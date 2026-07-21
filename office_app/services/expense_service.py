"""Expense and budget business logic independent of PyQt widgets."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from office_app.repositories.expense_repository import ExpenseRepository


class ExpenseService:
    """Coordinates expense validation, totals, and budget calculations."""

    ALL_YEARS = "All years"

    def __init__(self, repository: Optional[ExpenseRepository] = None) -> None:
        self.repository = repository or ExpenseRepository()

    def list_expenses(
        self,
        student_id: Any,
        school_year: Optional[str] = ALL_YEARS,
    ) -> List[Dict[str, Any]]:
        return self.repository.list_expenses(
            student_id,
            self._school_year_filter(school_year),
        )

    def add_expense(
        self,
        student_id: Any,
        description: str,
        amount: Any,
        expense_date: str,
        school_year: str,
    ) -> List[Dict[str, Any]]:
        payload = self.build_expense_payload(
            student_id=student_id,
            description=description,
            amount=amount,
            expense_date=expense_date,
            school_year=school_year,
        )
        return self.repository.insert_expense(payload)

    def delete_expense(self, expense_id: Any) -> List[Dict[str, Any]]:
        return self.repository.delete_expense(expense_id)

    def get_budget(self, student_id: Any, school_year: str) -> Optional[Dict[str, Any]]:
        if self._is_all_years(school_year):
            return None
        return self.repository.get_budget(student_id, school_year)

    def save_budget(
        self,
        student_id: Any,
        school_year: str,
        amount: Any,
    ) -> List[Dict[str, Any]]:
        if self._is_all_years(school_year):
            raise ValueError("Select a specific school year before saving a budget.")

        parsed_amount = self.parse_amount(amount)
        existing = self.repository.get_budget(student_id, school_year)
        if existing:
            return self.repository.update_budget(
                student_id,
                school_year,
                {"amount": parsed_amount},
            )
        return self.repository.insert_budget(
            {
                "student_id": student_id,
                "school_year": school_year,
                "amount": parsed_amount,
            }
        )

    def get_financial_summary(
        self,
        student_id: Any,
        school_year: Optional[str] = ALL_YEARS,
    ) -> Optional[Dict[str, Any]]:
        return self.repository.get_financial_summary(
            student_id,
            self._school_year_filter(school_year),
        )

    def get_financial_summaries(
        self,
        student_ids: List[Any],
        school_year: Optional[str] = ALL_YEARS,
    ) -> Dict[Any, Dict[str, Any]]:
        return self.repository.list_financial_summaries(
            student_ids,
            self._school_year_filter(school_year),
        )

    @staticmethod
    def build_expense_payload(
        student_id: Any,
        description: str,
        amount: Any,
        expense_date: str,
        school_year: str,
    ) -> Dict[str, Any]:
        desc = str(description or "").strip()
        if not student_id:
            raise ValueError("student_id is required.")
        if not desc:
            raise ValueError("Description is required.")
        if not expense_date:
            raise ValueError("Expense date is required.")
        if not school_year:
            raise ValueError("School year is required.")

        return {
            "student_id": student_id,
            "description": desc,
            "amount": ExpenseService.parse_amount(amount),
            "date": str(expense_date),
            "school_year": str(school_year),
        }

    @staticmethod
    def parse_amount(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value or "").replace(",", "").replace("PHP", "").strip()
        if not raw:
            raise ValueError("Amount is required.")
        amount = float(raw)
        if amount < 0:
            raise ValueError("Amount cannot be negative.")
        return amount

    @staticmethod
    def calculate_total(expenses: Iterable[Dict[str, Any]]) -> float:
        total = 0.0
        for expense in expenses:
            try:
                total += float(expense.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        return total

    @classmethod
    def budget_usage(cls, summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not summary:
            return {
                "budget": 0, "spent": 0, "percent": 0, "remaining": 0,
                "over_budget": False, "state": "neutral",
                "message": "No financial activity is available.",
            }

        spent = summary.get("total_expenses", 0)
        budget = summary.get("total_budget", 0)
        remaining = summary.get("remaining_balance", 0)
        if budget <= 0:
            return {
                "budget": budget, "spent": spent, "percent": 0,
                "remaining": remaining, "over_budget": False,
                "state": "neutral",
                "message": "No budget allocated for this school year.",
            }

        over_budget = remaining < 0

        percent = min(int((spent / budget) * 100), 100) if not over_budget else 100
        state = "danger" if over_budget else cls.budget_state(percent)

        if over_budget:
            message = (
                f"Over budget by PHP {abs(remaining):,.2f}  \u00b7  "
                f"PHP {spent:,.2f} spent of PHP {budget:,.2f}"
            )
        else:
            message = (
                f"{percent}% used  \u00b7  "
                f"PHP {spent:,.2f} of PHP {budget:,.2f}  \u00b7  "
                f"PHP {remaining:,.2f} remaining"
            )

        return {
            "budget": budget, "spent": spent, "percent": percent,
            "remaining": remaining, "over_budget": over_budget,
            "state": state, "message": message,
        }

    @classmethod
    def budget_card_status(cls, summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        usage = cls.budget_usage(summary)
        budget = usage["budget"]
        spent = usage["spent"]
        percent = usage["percent"]
        if budget <= 0:
            return {
                **usage,
                "allocated": False,
                "title": "No budget allocated",
                "detail": "",
            }
        return {
            **usage,
            "allocated": True,
            "title": f"{percent}% used",
            "detail": f"PHP {spent:,.0f} / {budget:,.0f}",
        }

    @staticmethod
    def budget_state(percent: int) -> str:
        if percent >= 100:
            return "danger"
        if percent >= 75:
            return "warning"
        return "success"

    @classmethod
    def total_label(cls, total: Any, school_year: Optional[str] = ALL_YEARS) -> str:
        sy_text = f" ({school_year})" if school_year and school_year != cls.ALL_YEARS else ""
        return f"Total{sy_text}: PHP {cls.parse_amount(total):,.2f}"

    @classmethod
    def _school_year_filter(cls, school_year: Optional[str]) -> Optional[str]:
        if not school_year or cls._is_all_years(school_year):
            return None
        return str(school_year)

    @classmethod
    def _is_all_years(cls, school_year: Optional[str]) -> bool:
        return str(school_year or "").strip().casefold() == cls.ALL_YEARS.casefold()
