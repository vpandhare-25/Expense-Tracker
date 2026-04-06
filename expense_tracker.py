#!/usr/bin/env python3
"""
Standalone expense tracker: add expenses to a pandas DataFrame and persist to CSV.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# CSV file lives next to this script so paths stay predictable when you run from anywhere.
CSV_FILENAME = "expenses.csv"
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH = SCRIPT_DIR / CSV_FILENAME

# Column names used everywhere so load, append, and save stay consistent.
COLUMNS = ["date", "category", "amount", "description"]


def category_spending_totals(df: pd.DataFrame) -> pd.Series:
    """
    Sum expense amounts grouped by category (same logic as text reports and bar/pie charts).

    Returns an empty Series if there are no rows with a valid amount.
    """
    valid = df.dropna(subset=["amount"])
    if valid.empty:
        return pd.Series(dtype=float)
    return valid.groupby("category", dropna=False)["amount"].sum().sort_values(ascending=False)


def monthly_spending_totals(df: pd.DataFrame) -> pd.Series:
    """
    Sum expense amounts grouped by calendar month (for monthly reports and line charts).

    Rows without a valid date are excluded. Returns an empty Series if nothing qualifies.
    """
    valid = df.dropna(subset=["amount", "date"])
    if valid.empty:
        return pd.Series(dtype=float)
    dated = valid.copy()
    dated["year_month"] = dated["date"].dt.to_period("M")
    return dated.groupby("year_month", sort=True)["amount"].sum()


def load_expenses() -> pd.DataFrame:
    """
    Start with an empty table or resume from disk.

    If expenses.csv exists, read it into a DataFrame.
    Otherwise create an empty DataFrame with the expected columns.
    """
    if CSV_PATH.is_file():
        # Read existing rows; pandas infers dtypes; we normalize types after load.
        df = pd.read_csv(CSV_PATH)
        # Ensure all expected columns exist (handles older files with fewer columns).
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA if col != "description" else ""
        df = df[COLUMNS]
        # Parse dates for consistent display and future filtering/sorting.
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        # Amounts should be numeric for totals later.
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        # Optional text field: use string dtype, fill missing with empty string.
        df["description"] = df["description"].fillna("").astype(str)
        df["category"] = df["category"].fillna("").astype(str)
        return df

    # No file yet: empty DataFrame with correct schema.
    return pd.DataFrame(columns=COLUMNS)


def save_expenses(df: pd.DataFrame) -> None:
    """
    Write the full DataFrame to expenses.csv after each change.

    index=False avoids writing an extra unnamed index column.
    """
    # Serialize dates as ISO date strings for readable CSV.
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(CSV_PATH, index=False)


def prompt_expense() -> Optional[Dict[str, Any]]:
    """
    Ask the user for one expense row.

    Returns a dict of field values, or None if the user cancels.
    """
    print("\n--- New expense (leave date blank for today) ---")

    # Date: optional blank means "today" for quicker entry.
    date_raw = input("Date (YYYY-MM-DD) [Enter=today]: ").strip()
    if date_raw:
        try:
            date_val = pd.to_datetime(date_raw).normalize()
        except (ValueError, TypeError):
            print("Invalid date. Use YYYY-MM-DD.")
            return None
    else:
        date_val = pd.Timestamp.today().normalize()

    # Category: required label for grouping (e.g. Food, Travel).
    category = input("Category: ").strip()
    if not category:
        print("Category cannot be empty.")
        return None

    # Amount: must parse as a positive number for this simple tracker.
    amount_raw = input("Amount: ").strip().replace(",", "")
    try:
        amount = float(amount_raw)
    except ValueError:
        print("Amount must be a number.")
        return None
    if amount < 0:
        print("Amount cannot be negative.")
        return None

    # Description: optional note; empty string is stored as blank.
    description = input("Description (optional): ").strip()

    return {
        "date": date_val,
        "category": category,
        "amount": amount,
        "description": description,
    }


def print_spending_summaries(df: pd.DataFrame) -> None:
    """
    Print total spending per category and per calendar month to the console.

    Both summaries sum the `amount` column; each expense row contributes its amount once.
    """
    if df.empty:
        print("No expenses to summarize.")
        return

    # --- Total spending per category ---
    # Group all rows that share the same `category` value, then sum `amount` within each group.
    # That sum is the total spent in that category across every date in the data.
    by_category = category_spending_totals(df)
    if by_category.empty:
        print("No expenses with valid amounts to summarize.")
        return

    print("\n=== Total spending per category ===")
    for category, total in by_category.items():
        print(f"  {category}: {total:,.2f}")
    # Sum of the per-category totals equals all counted expenses combined.
    print(f"  Grand total: {by_category.sum():,.2f}")

    # --- Total spending per month ---
    # For each calendar month bucket, sum `amount`: that is total spending in that month.
    by_month = monthly_spending_totals(df)
    if by_month.empty:
        print("\n(No rows with valid dates — skipping monthly summary.)")
        return

    print("\n=== Total spending per month ===")
    for year_month, total in by_month.items():
        print(f"  {year_month}: {total:,.2f}")


def plot_expense_charts(df: pd.DataFrame) -> None:
    """
    Build three figures with matplotlib/seaborn: bar by category, pie by category, line by month.

    Close each window to see the next. Uses the same totals as the text reports.
    """
    if df.empty:
        print("No expenses to chart.")
        return

    by_category = category_spending_totals(df)
    if by_category.empty or by_category.sum() == 0:
        print("No category totals to chart (need expenses with valid amounts).")
        return

    # Consistent fonts and light grid for readability across figures.
    sns.set_theme(style="whitegrid")

    # --- Bar chart: total expenses per category ---
    # Each bar's height is the sum of all amounts in that category — compares magnitudes across categories.
    bar_df = by_category.rename_axis("category").reset_index(name="total")
    bar_df["category"] = bar_df["category"].astype(str)
    plt.figure(figsize=(9, 4.5))
    ax = sns.barplot(
        data=bar_df,
        x="category",
        y="total",
        hue="category",
        palette="muted",
        legend=False,
    )
    ax.set_title("Total expenses per category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Total amount")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()

    # --- Pie chart: percentage of spending per category ---
    # Wedge area (and autopct labels) show each category's share of overall spending: part-to-whole.
    plt.figure(figsize=(7, 7))
    plt.pie(
        by_category.values,
        labels=by_category.index.astype(str),
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
    )
    plt.title("Percentage of spending per category")
    plt.tight_layout()
    plt.show()

    # --- Line chart: spending over time by month ---
    # X-axis is calendar month; each point's height is total spend that month — trend over time.
    by_month = monthly_spending_totals(df)
    if by_month.empty:
        print("No dated expenses — skipping monthly line chart.")
        return

    month_starts = by_month.index.to_timestamp()
    plt.figure(figsize=(9, 4.5))
    sns.lineplot(x=month_starts, y=by_month.values, marker="o", color="darkgreen", linewidth=2)
    plt.title("Total spending per month")
    plt.xlabel("Month")
    plt.ylabel("Total amount")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()


def main() -> None:
    """
    Load CSV if present, loop: add expenses and save after each one, until quit.
    """
    # Step 1: Load existing expenses from expenses.csv if the file exists;
    #         otherwise begin with an empty DataFrame with the right columns.
    expenses = load_expenses()
    src = CSV_PATH.name if CSV_PATH.is_file() else "(new file)"
    print(f"Loaded {len(expenses)} expense(s) from {src}.")

    while True:
        print("\nOptions: [a]dd, [s]how, [d]elete, [r]eports, [c]harts, [q]uit")
        choice = input("Choice: ").strip().lower()

        if choice in ("q", "quit", ""):
            # Step: Quit the program; nothing extra to save if user only viewed data.
            print("Goodbye.")
            break

        if choice in ("s", "show"):
            # Step: Print all rows currently in memory (same data as will be saved next time you add).
            if expenses.empty:
                print("No expenses yet.")
            else:
                print(expenses.to_string(index=False))
            continue

        if choice in ("d", "delete"):
            # Step: Remove one row by 1-based line number, then rewrite expenses.csv.
            if expenses.empty:
                print("Nothing to delete.")
                continue
            expenses = expenses.reset_index(drop=True)
            for i in range(len(expenses)):
                r = expenses.iloc[i]
                print(f"  {i + 1}. {r['date']} | {r['category']} | {r['amount']} | {r['description']}")
            raw = input(f"Row to delete (1–{len(expenses)}), or 0 to cancel: ").strip()
            try:
                n = int(raw)
            except ValueError:
                print("Enter a whole number.")
                continue
            if n == 0:
                continue
            if not (1 <= n <= len(expenses)):
                print("Row number out of range.")
                continue
            expenses = expenses.drop(index=n - 1).reset_index(drop=True)
            save_expenses(expenses)
            print(f"Deleted row {n}. {len(expenses)} row(s) left. Saved -> {CSV_PATH}")
            continue

        if choice in ("r", "reports", "report"):
            # Step: Print aggregates — totals by category and by calendar month (see function comments).
            print_spending_summaries(expenses)
            continue

        if choice in ("c", "charts", "chart", "v", "visualize"):
            # Step: Open bar, pie, and line charts (matplotlib/seaborn); close each window to continue.
            plot_expense_charts(expenses)
            continue

        if choice not in ("a", "add"):
            print("Unknown option.")
            continue

        # Step 2: Prompt for date, category, amount, and optional description.
        row = prompt_expense()
        if row is None:
            continue

        # Step 3: Append the new expense as a new row in the DataFrame.
        new_row = pd.DataFrame([row])
        expenses = pd.concat([expenses, new_row], ignore_index=True)

        # Step 4: Write the entire DataFrame back to expenses.csv so the file always matches memory.
        save_expenses(expenses)
        print(f"Saved. Total rows: {len(expenses)} -> {CSV_PATH}")


if __name__ == "__main__":
    main()
