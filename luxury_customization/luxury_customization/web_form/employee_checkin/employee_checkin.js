frappe.ready(function () {
	frappe.web_form.set_value("time", frappe.datetime.now_datetime());

	function fetchAndSetEmployeeInfo(value) {
		if (!value) {
			frappe.web_form.set_value("employee_name", "");
			frappe.web_form.set_value("employee_code", "");
			return;
		}
		frappe.call({
			method: "luxury_customization.api.employee_checkin.get_employee_info",
			args: { employee: value },
			callback: (r) => {
				if (r.message) {
					frappe.web_form.set_value("employee_name", r.message.employee_name || "");
					frappe.web_form.set_value("employee_code", r.message.employee_code || "");
				}
			},
		});
	}

	frappe.web_form.on("employee", (field, value) => {
		fetchAndSetEmployeeInfo(value);
	});

	// Add camera capture for employee_image field
	setTimeout(() => {
		const imageField = document.querySelector('[data-fieldname="employee_image"]');
		if (imageField && !imageField.querySelector('.camera-capture-btn')) {
			// Remove native "Attach" button — Take Photo is the only way to set employee_image
			const attachBtn = imageField.querySelector('.btn-attach');
			if (attachBtn) attachBtn.remove();
			// Create hidden file input with camera capture
			const cameraInput = document.createElement('input');
			cameraInput.type = 'file';
			cameraInput.accept = 'image/*';
			cameraInput.capture = 'environment';
			cameraInput.style.display = 'none';
			imageField.appendChild(cameraInput);

			// Create camera button
			const cameraBtn = document.createElement('button');
			cameraBtn.type = 'button';
			cameraBtn.className = 'btn btn-default btn-sm camera-capture-btn';
			cameraBtn.innerHTML = '<i class="fa fa-camera"></i> Take Photo';
			cameraBtn.style.marginLeft = '5px';

			cameraBtn.addEventListener('click', (e) => {
				e.preventDefault();
				cameraInput.click();
			});

			// Handle photo capture and upload
			cameraInput.addEventListener('change', (e) => {
				const file = e.target.files[0];
				if (file) {
					const reader = new FileReader();
					reader.onload = (event) => {
						// web_form.accept() (frappe core) expects Attach values as
						// "<filename>,<data-url>" — it splits on the first comma to
						// recover the file name, then decodes the data URL itself.
						// Sending the bare data URL makes "data:image/...;base64" the
						// file name instead of the payload prefix.
						frappe.web_form.set_value('employee_image', `${file.name},${event.target.result}`);
						frappe.msgprint('Photo captured successfully');
					};
					reader.readAsDataURL(file);
					cameraInput.value = '';
				}
			});

			// Insert button next to attach label
			const attachLabel = imageField.querySelector('.attach-label');
			if (attachLabel) {
				attachLabel.parentNode.insertBefore(cameraBtn, attachLabel.nextSibling);
			} else {
				imageField.appendChild(cameraBtn);
			}
		}
	}, 500);


	frappe.web_form.validate = () => {
		frappe.web_form.set_value("time", frappe.datetime.now_datetime());

		if (frappe.web_form.get_value("employee") && !frappe.web_form.get_value("employee_image")) {
			frappe.msgprint(__("Please upload your image before submitting Employee Checkin."));
			return false;
		}
		return true;
	};
});
