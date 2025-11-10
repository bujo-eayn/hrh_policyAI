"""
Streamlit frontend for HRH-PolicyAI.
Features authentication, chat interface, document management, and admin panel.
"""
import streamlit as st
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import os


# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# Page config
st.set_page_config(
    page_title="HRH-PolicyAI",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================================
# API Helper Functions
# ============================================================================

def extract_error_message(response) -> str:
    """Extract user-friendly error message from API response."""
    try:
        error_data = response.json()
        # Check for structured error response
        if isinstance(error_data, dict):
            # Try different possible error message fields
            if "message" in error_data:
                return error_data["message"]
            elif "detail" in error_data:
                return error_data["detail"]
            elif "error" in error_data:
                return error_data["error"]
        return str(error_data)
    except:
        # Fallback to generic messages based on status code
        status_code = response.status_code
        if status_code == 400:
            return "Invalid request. Please check your input."
        elif status_code == 401:
            return "Authentication failed. Please login again."
        elif status_code == 403:
            return "You don't have permission to perform this action."
        elif status_code == 404:
            return "The requested resource was not found."
        elif status_code == 500:
            return "Server error. Please try again later."
        else:
            return f"Request failed with status code {status_code}"


def api_request(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict] = None,
    files: Optional[Dict] = None,
    require_auth: bool = True
) -> Optional[Dict[str, Any]]:
    """Make API request with authentication."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {}

    if require_auth and "access_token" in st.session_state:
        headers["Authorization"] = f"Bearer {st.session_state.access_token}"

    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            if files:
                response = requests.post(url, headers=headers, data=data, files=files)
            else:
                response = requests.post(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return None

        if response.status_code == 401:
            # Token expired, try refresh
            if "refresh_token" in st.session_state:
                if refresh_access_token():
                    # Retry request with new token
                    return api_request(endpoint, method, data, files, require_auth)

        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        # Extract user-friendly error message
        error_msg = extract_error_message(e.response)
        st.error(error_msg)
        return None
    except requests.exceptions.ConnectionError:
        st.error("Connection error: Unable to reach the server. Please check if the backend is running.")
        return None
    except requests.exceptions.Timeout:
        st.error("Request timeout: The server is taking too long to respond.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Unexpected error: {str(e)}")
        return None


def refresh_access_token() -> bool:
    """Refresh access token using refresh token."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/refresh",
            json={"refresh_token": st.session_state.refresh_token}
        )
        response.raise_for_status()
        data = response.json()

        st.session_state.access_token = data["access_token"]
        st.session_state.refresh_token = data["refresh_token"]
        return True

    except:
        # Refresh failed, logout
        logout()
        return False


# ============================================================================
# Authentication Functions
# ============================================================================

def login(email: str, password: str) -> bool:
    """Login user and store tokens."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        data = response.json()

        st.session_state.access_token = data["access_token"]
        st.session_state.refresh_token = data["refresh_token"]
        st.session_state.logged_in = True

        # Get user info
        user_info = api_request("/auth/me")
        if user_info:
            st.session_state.user = user_info

        return True

    except requests.exceptions.HTTPError as e:
        # Extract user-friendly error message
        error_msg = extract_error_message(e.response)
        st.error(error_msg)
        return False
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to server. Please check if the backend is running.")
        return False
    except requests.exceptions.RequestException as e:
        st.error("Login failed. Please try again.")
        return False


def register(email: str, password: str, full_name: str) -> bool:
    """Register new user."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json={"email": email, "password": password, "full_name": full_name}
        )
        response.raise_for_status()
        st.success("Registration successful! Please login.")
        return True

    except requests.exceptions.HTTPError as e:
        # Extract user-friendly error message
        error_msg = extract_error_message(e.response)
        st.error(error_msg)
        return False
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to server. Please check if the backend is running.")
        return False
    except requests.exceptions.RequestException as e:
        st.error("Registration failed. Please try again.")
        return False


def logout():
    """Logout user and clear session."""
    for key in ["access_token", "refresh_token", "logged_in", "user"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# ============================================================================
# UI Pages
# ============================================================================

def show_login_page():
    """Display login/registration page."""
    st.title("🏥 HRH-PolicyAI")
    st.subheader("AI-Powered Policy Interpretation for Kenya's Health Workforce")

    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        st.subheader("Login")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                if not email or not password:
                    st.error("Please fill in all fields")
                elif login(email, password):
                    st.success("Login successful!")
                    st.rerun()

    with tab2:
        st.subheader("Register")
        with st.form("register_form"):
            reg_email = st.text_input("Email", key="reg_email")
            reg_name = st.text_input("Full Name")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            reg_password_confirm = st.text_input("Confirm Password", type="password")
            reg_submit = st.form_submit_button("Register")

            if reg_submit:
                if not reg_email or not reg_password or not reg_name:
                    st.error("Please fill in all fields")
                elif reg_password != reg_password_confirm:
                    st.error("Passwords do not match")
                elif len(reg_password) < 8:
                    st.error("Password must be at least 8 characters")
                elif register(reg_email, reg_password, reg_name):
                    st.balloons()

    # Demo credentials info
    st.info("""
    **Demo Credentials:**
    - Admin: admin@hrh-policy.ke / admin123
    - User: user@hrh-policy.ke / user123
    """)


def show_chat_page():
    """Display chat interface."""
    st.title("💬 Policy Q&A Chat")

    # Sidebar filters
    with st.sidebar:
        st.subheader("Query Options")

        regulatory_body = st.selectbox(
            "Filter by Regulatory Body",
            ["All"] + ["KMPDB", "NCK", "COC", "PPB", "PHOTC"]
        )

        top_k = st.slider("Number of sources", 1, 10, 5)

        if st.button("Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if "sources" in message and message["sources"]:
                with st.expander("📚 View Sources"):
                    for i, source in enumerate(message["sources"], 1):
                        st.markdown(f"**Source {i}: {source['document_title']}** ({source['regulatory_body']})")
                        st.markdown(f"*Similarity: {source['similarity_score']:.2%}*")
                        st.text(source['chunk_content'])
                        st.divider()

    # Chat input
    if prompt := st.chat_input("Ask a question about health workforce policies..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        # Get response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                query_data = {
                    "query": prompt,
                    "regulatory_body": None if regulatory_body == "All" else regulatory_body,
                    "top_k": top_k,
                    "include_sources": True
                }

                response = api_request("/chat/query", method="POST", data=query_data)

                if response:
                    st.markdown(response["answer"])

                    # Store assistant response
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response["answer"],
                        "sources": response.get("sources", [])
                    })

                    # Show metadata
                    st.caption(f"⏱️ {response['processing_time']:.2f}s | 🤖 {response['model_used']}")
                else:
                    st.error("Failed to get response from API")


def show_compare_page():
    """Display policy comparison interface."""
    st.title("🔄 Compare Policies")
    st.markdown("Compare policies across multiple regulatory bodies")

    # Select regulatory bodies
    bodies = st.multiselect(
        "Select Regulatory Bodies to Compare",
        ["KMPDB", "NCK", "COC", "PPB", "PHOTC"],
        default=["KMPDB", "NCK"]
    )

    # Query input
    query = st.text_area("What would you like to compare?", height=100)

    top_k_per_body = st.slider("Documents per body", 1, 5, 3)

    if st.button("Compare", type="primary"):
        if len(bodies) < 2:
            st.error("Please select at least 2 regulatory bodies")
        elif not query:
            st.error("Please enter a comparison query")
        else:
            with st.spinner("Analyzing policies..."):
                data = {
                    "query": query,
                    "regulatory_bodies": bodies,
                    "top_k_per_body": top_k_per_body
                }

                response = api_request("/chat/compare", method="POST", data=data)

                if response:
                    st.subheader("Comparative Analysis")
                    st.markdown(response["analysis"])

                    st.subheader("Source Documents")
                    for body, chunks in response["comparison"].items():
                        with st.expander(f"📄 {body}"):
                            if chunks:
                                for chunk in chunks:
                                    st.markdown(f"**{chunk['document_title']}**")
                                    st.markdown(f"*Similarity: {chunk['similarity_score']:.2%}*")
                                    st.text(chunk['content'][:300] + "...")
                                    st.divider()
                            else:
                                st.info("No relevant documents found")


def show_documents_page():
    """Display document management interface."""
    st.title("📚 Document Library")

    # Check if user is admin
    is_admin = st.session_state.get("user", {}).get("role") == "admin"

    # Upload section (admin only)
    if is_admin:
        with st.expander("📤 Upload New Document", expanded=False):
            with st.form("upload_form"):
                title = st.text_input("Document Title")
                regulatory_body = st.selectbox(
                    "Regulatory Body",
                    ["KMPDB", "NCK", "COC", "PPB", "PHOTC"]
                )
                file = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
                submit = st.form_submit_button("Upload & Process")

                if submit:
                    if not title or not file:
                        st.error("Please fill in all fields")
                    else:
                        with st.spinner("Uploading and processing document..."):
                            files = {"file": file}
                            data = {"title": title, "regulatory_body": regulatory_body}

                            response = api_request(
                                "/documents/upload",
                                method="POST",
                                data=data,
                                files=files
                            )

                            if response:
                                st.success("Document uploaded and processed successfully!")
                                st.rerun()

    # Filter
    filter_body = st.selectbox("Filter by Regulatory Body", ["All", "KMPDB", "NCK", "COC", "PPB", "PHOTC"])

    # List documents
    endpoint = "/documents" if filter_body == "All" else f"/documents?regulatory_body={filter_body}"
    documents = api_request(endpoint)

    if documents:
        st.info(f"Found {len(documents)} document(s)")

        for doc in documents:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"{doc['regulatory_body']} • {doc['chunk_count']} chunks • {doc['uploaded_at'][:10]}")

                with col2:
                    status = "✅ Processed" if doc['is_processed'] else "⏳ Processing"
                    st.markdown(status)

                with col3:
                    if is_admin:
                        if st.button("Delete", key=f"del_{doc['id']}"):
                            if api_request(f"/documents/{doc['id']}", method="DELETE"):
                                st.success("Document deleted")
                                st.rerun()

                st.divider()
    else:
        st.info("No documents found")


def show_admin_page():
    """Display admin dashboard."""
    st.title("⚙️ Admin Dashboard")

    # Get stats
    stats = api_request("/admin/stats")

    if stats:
        # Overview metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Users", stats["total_users"])
        with col2:
            st.metric("Total Documents", stats["total_documents"])
        with col3:
            st.metric("Total Chunks", stats["total_chunks"])

        # Documents by regulatory body
        st.subheader("Documents by Regulatory Body")
        st.bar_chart(stats["documents_by_regulatory_body"])

        # Recent uploads
        st.subheader("Recent Uploads")
        for doc in stats["recent_uploads"][:5]:
            st.markdown(f"- **{doc['title']}** ({doc['regulatory_body']}) - {doc['uploaded_at'][:10]}")

        # User list
        st.subheader("User Management")
        users = api_request("/admin/users")

        if users:
            for user in users["users"]:
                with st.container():
                    col1, col2, col3 = st.columns([2, 1, 1])

                    with col1:
                        st.markdown(f"**{user['email']}**")
                        st.caption(user.get('full_name', 'N/A'))

                    with col2:
                        st.markdown(f"Role: {user['role']}")

                    with col3:
                        status = "🟢 Active" if user['is_active'] else "🔴 Inactive"
                        st.markdown(status)

                    st.divider()


# ============================================================================
# Main App
# ============================================================================

def main():
    """Main application entry point."""
    # Check if logged in
    if not st.session_state.get("logged_in"):
        show_login_page()
        return

    # Sidebar navigation
    with st.sidebar:
        st.title("🏥 HRH-PolicyAI")

        user = st.session_state.get("user", {})
        st.markdown(f"**{user.get('full_name', 'User')}**")
        st.caption(f"{user.get('email', '')} ({user.get('role', 'user')})")

        st.divider()

        # Navigation
        pages = ["💬 Chat", "🔄 Compare Policies", "📚 Documents"]
        if user.get("role") == "admin":
            pages.append("⚙️ Admin")

        page = st.radio("Navigation", pages)

        st.divider()

        if st.button("Logout", type="primary"):
            logout()

    # Show selected page
    if page == "💬 Chat":
        show_chat_page()
    elif page == "🔄 Compare Policies":
        show_compare_page()
    elif page == "📚 Documents":
        show_documents_page()
    elif page == "⚙️ Admin":
        show_admin_page()


if __name__ == "__main__":
    main()
