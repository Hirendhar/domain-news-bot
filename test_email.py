"""
Quick Gmail SMTP credential test — instant pass/fail, no full bot run needed.

Run:  python test_email.py

It securely prompts for your Gmail address and App Password (input hidden),
strips spaces from the password, attempts a login, and optionally sends a
test email to yourself. Nothing is stored.
"""
import smtplib
import getpass
from email.mime.text import MIMEText


def main() -> None:
    addr = input("Gmail address: ").strip()
    raw = getpass.getpass("App Password (16 chars, paste — input hidden): ")
    pw = raw.replace(" ", "").strip()

    print(f"\nAddress: {addr}")
    print(f"Password length after stripping spaces: {len(pw)} chars (should be 16)")
    if len(pw) != 16:
        print("⚠️  WARNING: not 16 chars — this is probably NOT a valid App Password.")
        print("    Generate one at https://myaccount.google.com/apppasswords (needs 2-Step Verification ON).")

    print("\nAttempting login to smtp.gmail.com:465 ...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(addr, pw)
            print("✅ SUCCESS — Gmail accepted these credentials.\n")

            send = input("Send a test email to yourself to confirm delivery? [y/N]: ").strip().lower()
            if send == "y":
                msg = MIMEText("If you're reading this, your Domain News Bot email is working. 🌐")
                msg["Subject"] = "✅ Domain News Bot — email test"
                msg["From"] = addr
                msg["To"] = addr
                server.sendmail(addr, addr, msg.as_string())
                print(f"📨 Test email sent to {addr} — check your inbox.")
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ AUTH FAILED: {e}")
        print("\nMost likely causes:")
        print("  1. This is your normal Gmail password, not a 16-char App Password.")
        print("  2. 2-Step Verification is not enabled on this account.")
        print("  3. Wrong account — the App Password must belong to the address above.")
    except Exception as e:
        print(f"❌ FAILED: {e}")


if __name__ == "__main__":
    main()
