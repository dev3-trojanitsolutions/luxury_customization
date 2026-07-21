import frappe
from datetime import datetime, timedelta
from frappe.utils import today, getdate
import logging

logger = logging.getLogger("luxury_customization.company_documents")


def send_company_document_expiry_notifications():
	"""Daily scheduler job to send expiry notifications for Company Documents."""
	try:
		today_date = getdate(today())

		documents = frappe.get_all(
			"Company Documents",
			filters={"expiry_date": ["is", "set"]},
			fields=["name", "company", "document_name", "expiry_date"],
			limit_page_length=0
		)

		if not documents:
			logger.info("No Company Documents with expiry_date found")
			return

		for doc in documents:
			company_name = doc.get("company")
			if not company_name:
				continue

			# Fetch notification settings from linked Company record
			company = frappe.get_doc("Company", company_name)
			notify_days = int(company.get("notify_days") or 0)
			notify_users_field = company.get("notify_userd")

			# Skip if Company has no notification settings
			if not notify_days or not notify_users_field:
				continue

			# Extract user emails from the Table MultiSelect field
			notify_users = [u.get("user") for u in notify_users_field if u.get("user")]
			if not notify_users:
				continue

			expiry_date = getdate(doc["expiry_date"])
			notification_date = expiry_date - timedelta(days=notify_days)

			if today_date < notification_date or today_date > expiry_date:
				continue

			doc_name = doc.get("document_name", "N/A")

			days_remaining = (expiry_date - today_date).days
			days_text = "Expires Today" if days_remaining == 0 else f"{days_remaining} days"

			for user in notify_users:
				if not _user_exists_and_enabled(user):
					continue

				if _notification_sent_today(doc["name"], user):
					continue

				_send_notification(
					user,
					company_name,
					doc_name,
					doc["name"],
					expiry_date.strftime("%d-%m-%Y"),
					days_text
				)

				logger.info(f"Notification sent to {user} for {doc['name']}")

		logger.info(f"Company Document expiry notifications completed. Processed {len(documents)} documents")

	except Exception as e:
		logger.error(f"Error in send_company_document_expiry_notifications: {str(e)}", exc_info=True)
		frappe.log_error(title="Company Document Expiry Notification Error", message=str(e))


def _user_exists_and_enabled(user):
	"""Check if user exists and is enabled."""
	try:
		user_doc = frappe.get_doc("User", user)
		return not user_doc.get("disabled")
	except frappe.DoesNotExistError:
		return False


def _notification_sent_today(document_name, user):
	"""Check if notification already sent today for this document and user."""
	today_date = getdate(today())
	count = frappe.db.count(
		"Notification Log",
		filters={
			"document_name": document_name,
			"for_user": user,
			"subject": ["like", f"%{document_name}%"],
			"creation": [">=", f"{today_date} 00:00:00"],
			"creation": ["<", f"{today_date} 23:59:59"]
		}
	)
	return count > 0


def _send_notification(user, company_name, doc_name, document_name, expiry_date_str, days_text):
	"""Send system notification and email to user."""
	subject = f"Company Document Expiry Reminder - {company_name}"

	message = f"""
	<p><strong>Company Document Expiry Reminder</strong></p>
	<p><strong>Company:</strong> {frappe.utils.escape_html(company_name)}</p>
	<p><strong>Document:</strong> {frappe.utils.escape_html(doc_name)}</p>
	<p><strong>Expiry Date:</strong> {expiry_date_str}</p>
	<p><strong>Days Remaining:</strong> {days_text}</p>
	<p><a href="/app/company-documents/{frappe.utils.quote(document_name)}">View Document</a></p>
	"""

	notif = frappe.new_doc("Notification Log")
	notif.subject = subject
	notif.email_content = message
	notif.for_user = user
	notif.document_type = "Company Documents"
	notif.document_name = document_name
	notif.save(ignore_permissions=True)

	try:
		frappe.sendmail(
			recipients=[user],
			subject=subject,
			message=message,
			reference_doctype="Company Documents",
			reference_name=document_name
		)
	except Exception as e:
		logger.warning(f"Failed to send email to {user}: {str(e)}")
