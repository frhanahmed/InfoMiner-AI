import streamlit as st
from rag_engine import extract_urls_from_text, extract_data_from_sources, add_to_vector_store, query_rag_chat_stream

st.set_page_config(page_title="InfoMiner-AI", page_icon="💬", layout="wide")


# Session state setup
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "Hello! I am InfoMiner-AI. You can attach PDFs with the **+** icon, paste web links directly in the chat, or ask me any question."}
    ]
if "vector_store" not in st.session_state:
    st.session_state["vector_store"] = None
if "indexed_sources" not in st.session_state:
    st.session_state["indexed_sources"] = []


# Sidebar which will contain the history
with st.sidebar:
    st.header("🕒 Conversation")
    if st.button("🗑️ Reset Chat", use_container_width=True):
        st.session_state["messages"] = [
            {"role": "assistant", "content": "Chat reset! Feel free to attach new PDFs, paste links, or ask a question."}
        ]
        st.session_state["vector_store"] = None
        st.session_state["indexed_sources"] = []
        st.rerun()

    st.markdown("---")
    st.subheader("📚 Loaded Knowledge Sources")
    if st.session_state["indexed_sources"]:
        for src in st.session_state["indexed_sources"]:
            st.caption(f"• {src}")
    else:
        st.caption("No PDFs or links added yet.")


# Main Chat View
st.title("💬 InfoMiner-AI")
st.caption("Unified conversational RAG — attach files, paste links, or prompt directly.")

# Render previous messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input bar to give prompts
user_submission = st.chat_input(
    placeholder="Ask anything, paste links, or attach PDFs...",
    accept_file="multiple",
    file_type=["pdf"]
)

if user_submission:
    prompt_text = user_submission.text
    attached_files = user_submission.files

    # Parse URLs & PDFs
    detected_urls = extract_urls_from_text(prompt_text)

    if attached_files or detected_urls:
        with st.spinner("Processing attached sources for information...."):
            new_docs = extract_data_from_sources(attached_files, detected_urls)
            if new_docs:
                st.session_state["vector_store"] = add_to_vector_store(
                    new_docs, 
                    st.session_state["vector_store"]
                )
                for f in (attached_files or []):
                    st.session_state["indexed_sources"].append(f"📄 {f.name}")
                for u in detected_urls:
                    st.session_state["indexed_sources"].append(f"🔗 {u}")

    # Render user message
    display_user_msg = prompt_text
    if attached_files:
        file_names = ", ".join([f.name for f in attached_files])
        display_user_msg = f"*[Attached: {file_names}]*\n\n" + (prompt_text or "")

    st.session_state["messages"].append({"role": "user", "content": display_user_msg})
    with st.chat_message("user"):
        st.markdown(display_user_msg)

    # Stream AI's response
    with st.chat_message("assistant"):
        try:
            stream_gen = query_rag_chat_stream(
                st.session_state["vector_store"],
                st.session_state["messages"],
                prompt_text if prompt_text.strip() else "Summarize the attached document."
            )
            
            # Streams word-by-word directly to the screen
            full_response = st.write_stream(stream_gen)
            
            st.session_state["messages"].append({"role": "assistant", "content": full_response})
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")