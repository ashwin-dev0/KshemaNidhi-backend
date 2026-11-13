from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def schedule(principal, installments, method, start, annual_rate=12):
    principal = money(str(principal))
    remaining = principal
    monthly = money(principal / installments)
    accumulated = Decimal(0)
    rows = []

    def row(number, label, opening, due, interest, amount):
        offset = start.month - 1 + number
        year, month = start.year + offset // 12, offset % 12 + 1
        due_date = date(year, month, min(start.day, monthrange(year, month)[1]))
        return dict(number=number, label=label, dueDate=due_date.isoformat(), openingPrincipal=float(opening), principalDue=float(due), interestCalculated=float(interest), amountDue=float(amount), paid=False)

    for number in range(1, installments + 1):
        interest = money(remaining * Decimal(annual_rate) / 1200)
        if method == "REDUCING":
            due = remaining if number == installments else min(monthly, remaining)
            rows.append(row(number, f"Principal {number}", remaining, due, interest, due))
            remaining = money(remaining - due)
            accumulated += interest
        else:
            rows.append(row(number, f"Interest {number}", principal, 0, interest, interest))
    if method == "REDUCING":
        rows.append(row(installments + 1, "Interest settlement", 0, 0, accumulated, accumulated))
    else:
        rows.append(row(installments + 1, "Principal repayment", principal, principal, 0, principal))
    return rows
