import streamlit as st
import sqlite3

conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

# Ensure tables exist
cursor.execute("CREATE TABLE IF NOT EXISTS expense_lists (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, list_id INTEGER, name TEXT, amount REAL)")
conn.commit()

st.title("Budget App")

saved_income = st.number_input("Enter your income", min_value=0)

new_list = st.text_input("New expense list name")
if st.button("Create List"):
    cursor.execute("INSERT INTO expense_lists (user_id, name) VALUES (?, ?)", (1, new_list))
    conn.commit()
    st.success("List created")

cursor.execute("SELECT id, name FROM expense_lists WHERE user_id=?", (1,))
lists = cursor.fetchall()

if lists:
    list_dict = {name: list_id for list_id, name in lists}
    selected_list = st.selectbox("Select expense list", list_dict.keys())
    selected_list_id = list_dict[selected_list]

    st.subheader("➕ Add Expense")
    ename = st.text_input("Expense name")
    eamount = st.number_input("Amount", min_value=0)
    if st.button("Add Expense"):
        cursor.execute("INSERT INTO expenses (list_id, name, amount) VALUES (?, ?, ?)", (selected_list_id, ename, eamount))
        conn.commit()
        st.success("Expense added")

    st.subheader(f"📋 Expenses in {selected_list}")
    cursor.execute("SELECT name, amount FROM expenses WHERE list_id=?", (selected_list_id,))
    expenses = cursor.fetchall()
    total_expenses = sum(amount for _, amount in expenses)
    for name, amount in expenses:
        st.write(f"- {name}: ₦{amount}")

    balance = saved_income - total_expenses
    st.subheader("📊 Summary")
    st.write(f"Income: ₦{saved_income}")
    st.write(f"Expenses: ₦{total_expenses}")
    st.write(f"Balance: ₦{balance}")
else:
    st.info("Create an expense list to start adding expenses.")

