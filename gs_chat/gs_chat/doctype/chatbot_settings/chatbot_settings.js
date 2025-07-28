// Copyright (c) 2025, GWS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Chatbot Settings", {
    refresh(frm) {
        // Load available models when form loads
        load_available_models(frm);
    },

    provider(frm) {
        // Update models when provider changes
        if (frm.doc.provider) {
            load_models_for_provider(frm, frm.doc.provider);
        }
    }
});

function load_available_models(frm) {
    // Load models for all providers initially
    frappe.call({
        method: "gs_chat.controllers.chat.get_available_models",
        callback: function(r) {
            if (r.message && r.message.success) {
                // Store models data for later use
                frm._available_models = r.message.providers;

                // Set models for current provider
                if (frm.doc.provider) {
                    load_models_for_provider(frm, frm.doc.provider);
                }
            }
        }
    });
}

function load_models_for_provider(frm, provider) {
    if (frm._available_models && frm._available_models[provider]) {
        const provider_data = frm._available_models[provider];
        const models = provider_data.models;
        const default_model = provider_data.default_model;

        // Update model field options
        frm.set_df_property('model', 'options', models.join('\n'));

        // Set default model if current model is not valid for this provider
        if (!frm.doc.model || !models.includes(frm.doc.model)) {
            frm.set_value('model', default_model);
        }

        // Show/hide base_url field based on provider
        if (provider === 'DeepSeek') {
            frm.set_df_property('base_url', 'hidden', 0);
            if (!frm.doc.base_url) {
                frm.set_value('base_url', 'https://api.deepseek.com');
            }
        } else {
            frm.set_df_property('base_url', 'hidden', 1);
            frm.set_value('base_url', '');
        }

        frm.refresh_field('model');
        frm.refresh_field('base_url');
    }
}
