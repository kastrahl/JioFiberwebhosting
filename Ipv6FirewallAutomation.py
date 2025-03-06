from venv import logger
from playwright.sync_api import sync_playwright
import socket


def get_vm_ipv6():
    """Retrieve the IPv6 address of the VM."""
    try:
        addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)

        for addr in addresses:
            ip = addr[4][0]
            # Ignore link-local (starts with fe80::)
            if not ip.startswith("fe80::"):
                return ip  # Return first valid global IPv6
    except Exception as e:
        print(f"❌ Error fetching IPv6: {e}")
    return None


def delete_unwanted_rules(page, vm_ipv6):
    print("🔍 Checking firewall rules...")

    # Ensure the firewall rules table is visible before interacting
    page.wait_for_selector("#recordsData tbody tr", state="visible", timeout=0) 
    rules = page.locator("#recordsData tbody tr")  # Select all firewall rule rows
    rule_count = rules.count()

    if rule_count == 0:
        print("✅ No existing firewall rules found.")
        return False  # No rules exist, proceed with adding a new one

    print(f"⚠️ Found {rule_count} firewall rules. Checking if {vm_ipv6} already exists...")

    existing_rule_found = False #tracking current ipv6 rule

    try:
        #block to check if current ipv6 rule exists
        for i in range(rule_count):
            rule = rules.nth(i)  # Get the i-th rule row
            # Extract Destination IP (modify if your router UI structure differs)
            dest_ip = rule.locator("td").nth(6).inner_text().strip()
            if dest_ip == vm_ipv6:
                print(f"✅ Keeping rule with IP: {dest_ip}")
                existing_rule_found = True  # IPv6 rule exists, so exit the script 
            
        print("🚨 Current IPv6 rule not found! Deleting old rules...")


        #deletion block
        for i in range(rule_count):
            rule = rules.nth(i)  
            dest_ip = rule.locator("td").nth(6).inner_text().strip()

            # Skip deleting the current rule
            if dest_ip == vm_ipv6:
                print(f"⚡ Skipping deletion for current IP rule: {dest_ip}")
                continue


            print("⏳ Waiting for the page to fully load...")
            page.wait_for_load_state("networkidle")  # Ensures all requests are done
            print("✅ Page fully loaded! Now trying right-click...")
            print(f"🗑️ Attempting to delete rule with IP: {dest_ip}")

            # Right-click on the destination IP column
            print(f"🗑️ Right-clicking on rule with IP: {dest_ip}...")
            rule_locator = page.locator(f"td:has-text('{dest_ip}')")
            rule_locator.click(button="right")

            # Wait for the context menu to appear
            print("⏳ Waiting for the context menu...")
            page.wait_for_selector("#jqContextMenu", state="visible", timeout=5000)

            # Click the delete button
            print("🗑️ Clicking 'Delete' option...")
            page.locator("#deleteMenu").click()

            print("✅ Successfully clicked 'Delete'!")

            ip_column = page.locator(f"tr:has(td:has-text('{dest_ip}')) td:nth-child(7)")
            ip_column.first.click(button="right", force=True)
            page.wait_for_selector("#contextMenu", state="visible", timeout=0)
            page.locator("#deleteMenu").click()

            page.wait_for_timeout(2000)  # Small delay to avoid missing UI updates

        print("✅ Cleanup completed! Only the current rule remains (or will be added).")

    except Exception as e:
        print(f"❌ Error while deleting rules: {e}")

    
    return existing_rule_found  # Old rules were deleted, so proceed with adding the new one


def run():
    vm_ipv6 = get_vm_ipv6()
    if not vm_ipv6:
        print("❌ Failed to retrieve VM's IPv6 address.")
        return

    print(f"✅ VM's IPv6: {vm_ipv6}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Run in GUI mode
        context = browser.new_context()
        context.set_default_timeout(0)  # Disable timeouts
        page = context.new_page()

        try:
            #Step 1 - Log in 
            print("🔄 Opening router login page faster...")
            page.goto("http://192.168.29.1/platform.cgi", wait_until="domcontentloaded")  # ✅ Load only essential HTML
            print("🔑 Filling in login details...")
            page.fill("#tf1_userName", "admin")  # ✅ Replace with actual username
            page.fill("#tf1_password", "admin")  # ✅ Replace with actual password
            print("🚀 Clicking login button without waiting for full page load...")
            page.click(".loginBtn")  # ✅ Click login button immediately
            print("✅ Logged in! Now navigating to Firewall Settings...")



            #Step 2 - edge case of multiple admin log ins 
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5 * 1000)
            forced_login = page.locator("a.continue")
            if forced_login.is_visible():
                print("⚠️ Forced login detected! Clicking 'Continue'...")
                forced_login.click()
                page.wait_for_load_state("domcontentloaded")  
                print("✅ Continued successfully!")
                # Check if we got redirected to the login page instead of dashboard
                # if page.url.__contains__("login.html"):
                #     print("🚨 Detected forced logout! Logging in again...")

                #     # Re-enter login credentials
                #     page.fill("#tf1_userName", "admin")
                #     page.fill("#tf1_password", "")
                #     page.click(".loginBtn")

                #     # Ensure we are logged back in
                #     page.wait_for_load_state("domcontentloaded")
                #     print("✅ Re-logged in successfully!")
            print("✅ Login and forced login handling completed successfully!")


            #Step 3 - opening firewall menu
            page.evaluate("gotoLinks('firewallRulesIPv6.html')")  
            page.wait_for_load_state("domcontentloaded")  # ✅ Wait until page loads fully
            print("✅ Firewall rules page loaded successfully!")

            #Step 4 - Check if rule exists & exit early if needed
            if delete_unwanted_rules(page, vm_ipv6):
                print("✅ Firewall rule already exists! No changes needed. Exiting...")
                print("🔒 Logging out...")
                page.locator("#tf1_logoutAnchor").click()
                print("✅ Successfully logged out!")
                return  # 🚀 Exit early, no need to add a duplicate rule 
            
            #Step 4 - open ipv6 firewall settings 
            page.wait_for_selector("#tf1_security_defaultPolicy", state="visible")
            page.click("a[onclick*='firewallRulesIPv6.html']")
            page.wait_for_load_state("domcontentloaded")
            print("✅ Firewall page loaded!")


            #Step 5 - make new rule by Click "+ Add New" button
            page.click(".btnAddNew")
            print("🔄 Filling in firewall rule details...")

            # Set Direction: Inbound
            page.select_option("#tf1_direction", "Inbound")
            # Set Service: ANY
            page.select_option("#tf1_selSvrName", "ANY")
            # Set Action: Allow Always
            page.select_option("#tf1_selFwAction", "ACCEPT")
            # Set Schedule: No Schedule
            page.select_option("#tf1_schedules", "No Schedule")
            # Set Source IP: ANY
            page.select_option("#tf1_addFwSrcUser", "0") #"0" corresponds to "Any"
            # Set Destination IP: Single Address
            page.select_option("#tf1_destinationHost", "1")  #"1" corresponds to "Single Address"
            # Wait for Destination IP input field to appear
            page.wait_for_selector("#tf1_destinationHostStart", state="visible")
            page.click("#tf1_destinationHostStart")
            # Enter VM's IPv6
            page.type("#tf1_destinationHostStart", vm_ipv6, delay=50)
            print(f"✅ IPv6 {vm_ipv6} entered successfully!")
            page.click("input[name='button.config.firewallRulesIPv6.firewallRulesIPv6.-1']")
            print("✅ Firewall rule added successfully!")

            #Step 6 - Log out
            # page.locator(".dropbtn").hover(force=True)
            # page.evaluate("document.querySelector('.dropdown-content').style.display = 'block'")
            # page.wait_for_selector(".dropdown-content", state="visible")
            # print("🔒 Logging out...")
            # page.locator("#tf1_logoutAnchor").click()
            # print("✅ Successfully logged out!")

            # print("🔄 Trying to open the logout dropdown...")
            # # Click the profile dropdown to open the menu
            # profile_dropdown = page.locator(".dropbtn")
            # profile_dropdown.click()
            # # Wait for the dropdown to appear
            # page.wait_for_selector(".dropdown-content", state="visible")
            # # Click the logout button
            # print("🔒 Clicking logout...")
            # page.locator("#tf1_logoutAnchor").click()
            # print("✅ Successfully logged out!")


        except Exception as e:
            print(f"❌ An error occurred: {e}")

        print("🔄 Waiting for 10 seconds before closing the browser...")
        page.wait_for_timeout(0)
        browser.close()

if __name__ == "__main__":
    run()
