"""
Streamlit web UI for the expense tracker.

Run from the project directory:
    streamlit run main.py

Uses the same pandas DataFrame shape, `expenses.csv` path, and helpers as `expense_tracker.py`.
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

# Reuse CSV load/save and aggregation logic so CLI and web app stay in sync.
from expense_tracker import (
    CSV_PATH,
    category_spending_totals,
    load_expenses,
    monthly_spending_totals,
    save_expenses,
)

# --- Page setup: browser tab title and layout ---
st.set_page_config(page_title="Expense Tracker", layout="wide")
st.title("Expense Tracker")
st.caption(f"Data file: `{CSV_PATH.name}` (same storage as the CLI script).")

# After st.rerun(), normal st.success in the sidebar would disappear; flag survives one run.
if st.session_state.pop("expense_saved", False):
    st.success("Expense saved.")
if st.session_state.pop("expense_deleted", False):
    st.success("Expense deleted.")

# --- Load current expenses from disk on every run ---
# Streamlit reruns the script on each interaction; reading the CSV keeps the UI aligned with the file.
df = load_expenses()

# ---------------------------------------------------------------------------
# Section: Add expense (form)
# ---------------------------------------------------------------------------
# st.form batches inputs and submits once, avoiding partial reruns while typing.
with st.sidebar:
    st.header("Add expense")
    with st.form("expense_form", clear_on_submit=True):
        # Date of the transaction; defaults to today for quick entry.
        expense_date = st.date_input("Date", value=date.today())
        # Category groups rows for summaries and charts (required).
        category = st.text_input("Category")
        # Numeric amount; min_value prevents negative entries matching CLI rules.
        amount = st.number_input("Amount", min_value=0.0, format="%.2f", step=0.01)
        # Optional free-text note stored in the DataFrame and CSV.
        description = st.text_input("Description (optional)")
        submitted = st.form_submit_button("Save expense")

    if submitted:
        if not (category or "").strip():
            st.error("Category is required.")
        else:
            # Build one row dict compatible with load_expenses / save_expenses dtypes.
            new_row = pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp(expense_date),
                        "category": category.strip(),
                        "amount": float(amount),
                        "description": (description or "").strip(),
                    }
                ]
            )
            # Reload from disk right before append so concurrent edits are less likely to be lost.
            updated = pd.concat([load_expenses(), new_row], ignore_index=True)
            save_expenses(updated)
            st.session_state["expense_saved"] = True
            st.rerun()

    # Pick a row by its position in the CSV (1st row = top of the table below), then remove it and save.
    if not df.empty:
        st.divider()
        st.header("Delete expense")

        def _row_label(i: int) -> str:
            r = df.iloc[i]
            dt = pd.to_datetime(r["date"], errors="coerce")
            ds = dt.strftime("%Y-%m-%d") if pd.notna(dt) else "?"
            desc = (r["description"] or "")[:40]
            return f"{i + 1}. {ds} | {r['category']} | {float(r['amount']):,.2f} | {desc}"

        pick = st.selectbox(
            "Select expense to remove",
            options=list(range(len(df))),
            format_func=_row_label,
            key="delete_pick",
        )
        if st.button("Delete selected expense", type="primary"):
            fresh = load_expenses().reset_index(drop=True)
            if 0 <= pick < len(fresh):
                fresh = fresh.drop(index=pick).reset_index(drop=True)
                save_expenses(fresh)
                st.session_state["expense_deleted"] = True
                st.rerun()

# ---------------------------------------------------------------------------
# Section: Raw data table
# ---------------------------------------------------------------------------
st.subheader("All expenses")
if df.empty:
    st.info("No expenses yet. Add one using the sidebar form.")
else:
    # Display the same columns persisted to CSV; index hidden for readability.
    display_df = df.copy()
    display_df["date"] = pd.to_datetime(display_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section: Text summaries (interactive tables)
# ---------------------------------------------------------------------------
st.subheader("Summaries")

by_category = category_spending_totals(df)
by_month = monthly_spending_totals(df)

col_cat, col_month = st.columns(2)

with col_cat:
    st.markdown("**Total spending per category**")
    # Each row is one category; the Total column is the sum of amount for that category.
    if by_category.empty:
        st.caption("No data with valid amounts.")
    else:
        cat_table = by_category.rename_axis("Category").reset_index(name="Total")
        st.dataframe(cat_table, use_container_width=True, hide_index=True)
        st.metric("Grand total", f"{by_category.sum():,.2f}")

with col_month:
    st.markdown("**Total spending per month**")
    # Each row is one calendar month; Total is the sum of expenses in that month.
    if by_month.empty:
        st.caption("No data with valid dates and amounts.")
    else:
        month_table = by_month.rename_axis("Month").reset_index(name="Total")
        month_table["Month"] = month_table["Month"].astype(str)
        st.dataframe(month_table, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section: Charts (Plotly — hover, zoom, pan in the browser)
# ---------------------------------------------------------------------------
st.subheader("Charts")

if by_category.empty or by_category.sum() == 0:
    st.info("Add expenses with amounts to see category charts.")
else:
    # Prepare a tidy frame: one row per category with its summed total (same as bar/pie input).
    chart_cat = by_category.rename_axis("category").reset_index(name="total")
    chart_cat["category"] = chart_cat["category"].astype(str)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Bar chart: compare total spend per category (bar height = sum of amounts in that category).
        fig_bar = px.bar(
            chart_cat,
            x="category",
            y="total",
            title="Total expenses per category",
            labels={"category": "Category", "total": "Total amount"},
        )
        fig_bar.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        # Pie chart: each slice’s angle shows that category’s share of overall spending (percent of whole).
        fig_pie = px.pie(
            chart_cat,
            values="total",
            names="category",
            title="Percentage of spending per category",
        )
        st.plotly_chart(fig_pie, use_container_width=True)

if by_month.empty:
    st.info("Add expenses with valid dates to see the monthly trend chart.")
else:
    # Line chart: x = month, y = total spend that month — shows spending trend over time.
    chart_month = by_month.rename_axis("month").reset_index(name="total")
    chart_month["month"] = chart_month["month"].astype(str)
    fig_line = px.line(
        chart_month,
        x="month",
        y="total",
        markers=True,
        title="Total spending per month",
        labels={"month": "Month", "total": "Total amount"},
    )
    fig_line.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_line, use_container_width=True)
