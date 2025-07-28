#!/usr/bin/env python3
"""
Setup script to configure DeepSeek AI for GS Chat
"""

import frappe

def setup_deepseek_settings(api_key):
    """
    Configure the chatbot settings to use DeepSeek AI
    
    Args:
        api_key (str): Your DeepSeek API key
    """
    try:
        # Get or create the Chatbot Settings document
        if frappe.db.exists("Chatbot Settings", "Chatbot Settings"):
            settings = frappe.get_doc("Chatbot Settings", "Chatbot Settings")
        else:
            settings = frappe.new_doc("Chatbot Settings")
            settings.name = "Chatbot Settings"
        
        # Configure for DeepSeek
        settings.provider = "DeepSeek"
        settings.api_key = api_key
        settings.base_url = "https://api.deepseek.com"
        settings.model = "deepseek-chat"  # Default to deepseek-chat model
        
        # Save the settings
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        
        print("✅ DeepSeek configuration saved successfully!")
        print(f"   Provider: {settings.provider}")
        print(f"   Model: {settings.model}")
        print(f"   Base URL: {settings.base_url}")
        print(f"   API Key: {api_key[:8]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error configuring DeepSeek: {str(e)}")
        return False

def main():
    """
    Main function to run the setup
    """
    print("🚀 DeepSeek AI Setup for GS Chat")
    print("=" * 40)
    
    # Your DeepSeek API key
    api_key = "sk-ae2bfc754a4040e595a2acbcdf7483f5"
    
    if not api_key:
        print("❌ Please provide your DeepSeek API key")
        return
    
    # Initialize Frappe
    frappe.init()
    frappe.connect()
    
    # Setup DeepSeek
    success = setup_deepseek_settings(api_key)
    
    if success:
        print("\n🎉 Setup completed! You can now use DeepSeek AI in your chatbot.")
        print("\nAvailable DeepSeek models:")
        print("  - deepseek-chat (DeepSeek-V3-0324)")
        print("  - deepseek-reasoner (DeepSeek-R1-0528)")
        print("\nTo change the model, update the 'Model' field in Chatbot Settings.")
    else:
        print("\n❌ Setup failed. Please check the error messages above.")

if __name__ == "__main__":
    main()
