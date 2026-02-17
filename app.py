import streamlit as st
import sqlite3

# Database setup
conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

# Example: income input
saved_income = st.number_input("Enter your income", min_value=0)

# Create new list
new_list = st.text_input("New expense list name")
if st.button("Create List"):
    cursor.execute(
        "INSERT INTO expense_lists (user_id, name) VALUES (?, ?)",
        (1, new_list)  # replace 1 with actual user_id logic
    )
    conn.commit()
    st.success("List created")

# Fetch lists
cursor.execute("SELECT id, name FROM expense_lists WHERE user_id=?", (1,))
lists = cursor.fetchall()

if not lists:
    st.info("Create an expense list to start adding expenses.")
    st.stop()

list_dict = {name: list_id for list_id, name in lists}
selected_list = st.selectbox("Select expense list", list_dict.keys())
selected_list_id = list_dict[selected_list]

# Add expense
st.subheader("➕ Add Expense")
ename = st.text_input("Expense name")
eamount = st.number_input("Amount", min_value=0)

if st.button("Add Expense"):
    if ename and eamount > 0:
        cursor.execute(
            "INSERT INTO expenses (list_id, name, amount) VALUES (?, ?, ?)",
            (selected_list_id, ename, eamount)
        )
        conn.commit()
        st.success("Expense added")

# Display expenses
st.subheader(f"📋 Expenses in {selected_list}")
cursor.execute("SELECT name, amount FROM expenses WHERE list_id=?", (selected_list_id,))
expenses = cursor.fetchall()

total_expenses = sum(amount for _, amount in expenses)
for name, amount in expenses:
    st.write(f"- {name}: ₦{amount}")

balance = saved_income - total_expenses

# Summary
st.subheader("📊 Summary")
st.write(f"Income: ₦{saved_income}")
st.write(f"Expenses (this list): ₦{total_expenses}")
st.write(f"Balance: ₦{balance}")

