"""Synthetic bank SMS fixtures from SPEC Appendix D (illustrative only)."""

CREDIT_STYLE_1 = ("VM-DEMOBK", "Rs 114.63 credited to A/c XXXXXX1234 on 20-09-26 by UPI Ref No 123456789012. -DEMO BANK")
CREDIT_STYLE_2 = (
    "VM-OKAXIS",
    "Your a/c XX1234 is credited with INR 60.00 on 20/09/2026 from rahul@okaxis (UPI Ref 210987654321). Avl bal INR 5,431.20",
)
CREDIT_STYLE_3 = ("VM-DEMOB3", "UPI/CR/345678901234/RAHUL K/DEMO/20-09-2026 Rs.85.40 credited to XX1234")
CREDIT_STYLE_4 = (
    "VM-DEMOB4",
    "Dear Customer, INR 45.50 received in your account XXXX1234 via UPI on 20-Sep-26. UTR: 456789012345",
)
DEBIT_SMS = ("VM-DEMOBK", "Rs 500.00 debited from A/c XXXXXX1234 on 20-09-26 UPI Ref No 999999999999.")
OTP_SMS = ("VM-DEMOBK", "123456 is your OTP for login. Do not share with anyone.")
