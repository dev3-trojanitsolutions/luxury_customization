frappe.ready(function () {
	frappe.web_form.set_value("time", frappe.datetime.now_datetime());

	// Cache for employee names
	window._employeeCache = {};

	// Custom dropdown formatting for Employee field
	setTimeout(() => {
		const employeeInput = document.querySelector('[data-fieldname="employee"] input');
		if (employeeInput) {
			// Watch for dropdown changes
			const dropdownParent = employeeInput.parentElement;
			const observer = new MutationObserver(() => {
				const dropdown = dropdownParent.querySelector('ul');
				if (dropdown) {
					updateDropdownItems(dropdown);
				}
			});

			observer.observe(dropdownParent, { childList: true, subtree: true });

			// Also listen to input events
			employeeInput.addEventListener('input', () => {
				setTimeout(() => {
					const dropdown = dropdownParent.querySelector('ul');
					if (dropdown) {
						updateDropdownItems(dropdown);
					}
				}, 100);
			});
		}
	}, 200);

	function updateDropdownItems(dropdown) {
		const items = dropdown.querySelectorAll('li');
		const needsFetch = [];

		items.forEach(item => {
			const empCode = item.textContent.trim();
			if (empCode && !window._employeeCache[empCode]) {
				needsFetch.push(empCode);
			}
		});

		if (needsFetch.length > 0) {
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Employee",
					filters: { name: ["in", needsFetch] },
					fields: ["name", "employee_name"],
					limit_page_length: 100
				},
				callback: (r) => {
					if (r.message) {
						r.message.forEach(emp => {
							window._employeeCache[emp.name] = emp.employee_name;
						});
						renderDropdown(dropdown);
					}
				}
			});
		} else {
			renderDropdown(dropdown);
		}
	}

	function renderDropdown(dropdown) {
		const items = dropdown.querySelectorAll('li');
		items.forEach(item => {
			const empCode = item.textContent.trim();
			const empName = window._employeeCache[empCode] || '';
			if (empName) {
				item.innerHTML = `<strong>${empCode}</strong><br/><span style="font-size: 0.85em; color: #666;">${empName}</span>`;
			}
		});
	}

	frappe.web_form.on("employee", (field, value) => {
		if (!value) {
			frappe.web_form.set_value("employee_name", "");
			frappe.web_form.set_value("employee_code", "");
			return;
		}
		frappe.call({
			method: "luxury_customization.api.employee_checkin.get_employee_details",
			args: { employee: value },
			callback: (r) => {
				frappe.web_form.set_value("employee_name", r.message?.employee_name || "");
				frappe.web_form.set_value("employee_code", r.message?.employee_number || "");
			},
		});
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
						frappe.web_form.set_value('employee_image', event.target.result);
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
