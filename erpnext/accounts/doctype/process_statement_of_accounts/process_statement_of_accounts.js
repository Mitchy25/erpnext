// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Process Statement Of Accounts", {
	view_properties: function (frm) {
		frappe.route_options = { doc_type: "Customer" };
		frappe.set_route("Form", "Customize Form");
	},
	refresh: function(frm){
		if(!frm.doc.__islocal) {
			// frm.add_custom_button('Send Emails',function(){
			// 	if (frm.doc.__islocal != 1) frm.save();
			// 	frappe.confirm('You are about to send Customer Statements. <span style="color:red;font-weight:bold;">This action is not reversible</span>. Please make sure that the following details are correct:<br><br><b>From:</b> ' + frm.doc.from_date + "<br><b>To:</b> " + frm.doc.to_date,
			// 		function() {
			// 			// if Yes
			// 			frappe.show_alert({message: __('Please wait...'), indicator: 'orange'});
			// 			frappe.call({
			// 				"method": "frappe.desk.form.utils.add_comment",
			// 				"args": {
			// 				  reference_doctype: "Process Statement Of Accounts",
			// 				  reference_name: frm.doc.name,
			// 				  content: "Statement send executed by " + frappe.user.name + " at " + frappe.datetime.now_datetime() + ".<br><br>From: " + frm.doc.from_date + ".<br>To: " + frm.doc.to_date + ".",
			// 				  comment_email: frappe.session.user,
			// 				  comment_by: frappe.session.user_fullname,
			// 				}
			// 			});
			// 			frappe.call({
			// 				method: "erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.send_emails",
			// 				args: {
			// 					"document_name": frm.doc.name,
			// 				},
			// 				callback: function(r) {
			// 					if(r && r.message) {
			// 						frappe.show_alert({message: __('Emails Queued'), indicator: 'blue'});
			// 					}
			// 					else{
			// 						frappe.msgprint(__('No Records for these settings.'))
			// 					}
			// 				}
			// 			});
			// 		},
			// 		function() {
			// 			// if No
			// 			frappe.show_alert({
			// 				message: 'Aborted',
			// 				indicator: 'red'
			// 			});
			// 		}
			// 	);
			// });
			
			frm.add_custom_button('Download',function(){
				if (frm.doc.__islocal != 1) frm.save();
				// var url = frappe.urllib.get_full_url(
				// 	'/api/method/erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.download_statements?'
				// 	+ 'document_name='+encodeURIComponent(frm.doc.name))
				// $.ajax({
				// 	url: url,
				// 	type: 'GET',
				// 	success: function(result) {
				// 		if(jQuery.isEmptyObject(result)){
				// 			frappe.msgprint(__('No Records for these settings.'));
				// 		}
				// 		else{
				// 			window.location = url;
				// 		}
				// 	}
				// });
				alert("Please use the 'Download PDF' button in the rows below")
			});
		}
	},
	onload: function (frm) {
		frm.set_query("currency", function () {
			return {
				filters: {
					enabled: 1,
				},
			};
		});
		frm.set_query("account", function() {
			return {
				filters: {
					'company': frm.doc.company
				}
			};
		});
		if(frm.doc.__islocal){
			frm.set_value('from_date', frappe.datetime.add_months(frappe.datetime.get_today(), -1));
			frm.set_value('to_date', frappe.datetime.get_today());
		}
	},
	report: function (frm) {
		let filters = {
			company: frm.doc.company,
		};
		if (frm.doc.report == "Accounts Receivable") {
			filters["account_type"] = "Receivable";
		}
		frm.set_query("account", function () {
			return {
				filters: filters,
			};
		});
	},
	customer_collection: function (frm) {
		frm.set_value("collection_name", "");
		if (frm.doc.customer_collection) {
			frm.get_field("collection_name").set_label(frm.doc.customer_collection);
		}
	},
	frequency: function (frm) {
		if (frm.doc.frequency != "") {
			frm.set_value("start_date", frappe.datetime.get_today());
		} else {
			frm.set_value("start_date", "");
		}
	},
	fetch_customers: function(frm){
		if (frm.doc.customer_collection == "Custom Logic"){
            var customLogic = frm.doc.logic
        } else {
            var customLogic = null
        }

		if(frm.doc.collection_name || (frm.doc.customer_collection == "Custom Logic" && frm.doc.logic)){
			frappe.call({
				method: "erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.fetch_customers",
				args: {
					'customer_collection': frm.doc.customer_collection,
					'collection_name': frm.doc.collection_name,
					'primary_mandatory': frm.doc.primary_mandatory,
                    'custom_logic': customLogic
				},
				callback: function (r) {
					if (!r.exc) {
						if (r.message.length) {
							frm.clear_table("customers");
							for (const customer of r.message) {
								var row = frm.add_child("customers");
								row.customer = customer.name;
								row.primary_email = customer.primary_email;
								row.billing_email = customer.billing_email;
							}
							frm.refresh_field('customers');
							frm.save()
						}
						else{
							frappe.throw(__('No Customers found with selected options.'));
						}
					}
				},
			});
		} else {
			frappe.throw("Enter " + frm.doc.customer_collection + " name.");
		}
	},
});

frappe.ui.form.on("Process Statement Of Accounts Customer", {
	customer: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (!row.customer) {
			return;
		}
		frappe.call({
			method: "erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.get_customer_emails",
			args: {
				customer_name: row.customer,
				primary_mandatory: frm.doc.primary_mandatory,
			},
			callback: function (r) {
				if (!r.exe) {
					if (r.message.length) {
						frappe.model.set_value(cdt, cdn, "primary_email", r.message[0]);
						frappe.model.set_value(cdt, cdn, "billing_email", r.message[1]);
					} else {
						return;
					}
				}
			},
		});
	},
});
