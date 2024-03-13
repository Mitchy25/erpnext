// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bank Account', {
	before_save: function (frm) {
		if (frm.doc.company === "Therahealth" || frm.doc.company === "RN Labs") { //AUS
			let branch_code = frm.doc.branch_code.replace(/-|\s/g,"");
			if (!branch_code.match(/^[0-9-]+$/)) {
				frappe.msgprint("Branch Codes should only contain numbers and a hypen")
				frappe.msgprint = false;
			} else if (branch_code.length < 6) {
				frappe.msgprint("Branch Code is too short, Please provide one in format: XXX-XXX")
				frappe.validated = false;
			} else if (branch_code.length > 6) {
				frappe.msgprint("Branch Code is too long, Please provide one in format: XXX-XXX");
				frappe.validated = false;
			}
			let account_no = frm.doc.bank_account_no.replace(/-|\s/g,"");
			if (!account_no.match((/^[0-9-]+$/))) {
				frappe.msgprint("Bank Account Numbers should only contain numbers.")
				frappe.validated = false
			} else if (account_no.length < 6) {
				frappe.msgprint("Bank Account Number is too short, please provide one that is at least 6 numbers long.")
				frappe.validated = false
			} else if (account_no.length > 10) {
				frappe.msgprint("Bank Account Number is too long, please provide one that is 9 numbers long.")
				frappe.validated = false
			}
		} else if (frm.doc.company == "NaturalMeds") { //NZD
			let account_no = frm.doc.bank_account_no.replace(/-|\s/g,"");
			if (!account_no.match(/^[0-9-]+$/)) {
				frappe.msgprint("Bank Account Numbers should only contain numbers and hypens")
				frappe.validated = false
			} else if (account_no.length < 15) {
				frappe.msgprint("Bank Account Number is too short, Please provide one in format: XX-XXXX-XXXXXXXX-XX(X)")
				frappe.validated = false
			} else if (account_no.length > 16) {
				frappe.msgprint("Bank Account Number is too long, Please provide one in format: XX-XXXX-XXXXXXXX-XXX")
				frappe.validated = false
			}
		}
	},

	setup: function(frm) {
		frm.set_query("account", function() {
			return {
				filters: {
					'account_type': 'Bank',
					'company': frm.doc.company,
					'is_group': 0
				}
			};
		});
		frm.set_query("party_type", function() {
			return {
				query: "erpnext.setup.doctype.party_type.party_type.get_party_type",
			};
		});
	},
	refresh: function(frm) {
		frappe.dynamic_link = { doc: frm.doc, fieldname: 'name', doctype: 'Bank Account' }

		frm.toggle_display(['address_html','contact_html'], !frm.doc.__islocal);

		if (frm.doc.__islocal) {
			frappe.contacts.clear_address_and_contact(frm);
		}
		else {
			frappe.contacts.render_address_and_contact(frm);
		}

		if (frm.doc.integration_id) {
			frm.add_custom_button(__("Unlink external integrations"), function() {
				frappe.confirm(__("This action will unlink this account from any external service integrating ERPNext with your bank accounts. It cannot be undone. Are you certain ?"), function() {
					frm.set_value("integration_id", "");
				});
			});
		}
	},

	is_company_account: function(frm) {
		frm.set_df_property('account', 'reqd', frm.doc.is_company_account);
	}
});
