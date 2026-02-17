import streamlit as st

st.set_page_config(page_title="Test App", page_icon="✅")

st.title("✅ Streamlit is Working")

st.write("If you can see this text, Streamlit is rendering correctly.")

name = st.text_input("Type something")

if name:
    st.success(f"You typed: {name}")
import streamlit as st

st.set_page_config(page_title="Test App", page_icon="✅")

st.title("✅ Streamlit is Working")

st.write("If you can see this text, Streamlit is rendering correctly.")

name = st.text_input("Type something")

if name:
    st.success(f"You typed: {name}")



