import streamlit as st
from passlib.context import CryptContext
from typing import Optional, Dict
import db # Import your database module
import logging

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain text password."""
    return pwd_context.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a hashed password."""
    return pwd_context.verify(password, hashed_password)

def register_user(username: str, password: str, name: str, role: str = "citizen", preferred_location: Optional[str] = None) -> bool:
    """
    Registers a new user.
    Returns True on success, False if username already exists or other error.
    """
    if db.get_user_by_username(username):
        st.error("Username already exists. Please choose a different one.")
        logger.warning(f"Registration failed: Username '{username}' already exists.")
        return False
    
    hashed_password = hash_password(password)
    
    user_data = {
        "id": username, # Using username as id for simplicity
        "username": username,
        "password_hash": hashed_password,
        "name": name,
        "role": role,
        "preferred_location": preferred_location
    }
    
    try:
        db.insert_or_update_user(user_data)
        st.success("Registration successful! You can now log in.")
        logger.info(f"User '{username}' registered successfully with role '{role}'.")
        return True
    except Exception as e:
        st.error(f"An error occurred during registration: {e}")
        logger.exception(f"Error during registration for user '{username}'.")
        return False

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """
    Authenticates a user.
    Returns user details (excluding password hash) on success, None on failure.
    """
    user_data = db.get_user_by_username(username)
    
    if user_data and verify_password(password, user_data["password_hash"]):
        # Remove password hash before returning user data
        user_data.pop("password_hash")
        st.success(f"Welcome, {user_data['name']}!")
        logger.info(f"User '{username}' authenticated successfully.")
        return user_data
    else:
        st.error("Invalid username or password.")
        logger.warning(f"Authentication failed for username '{username}'.")
        return None

def get_user_details(username: str) -> Optional[Dict]:
    """
    Retrieves user details (excluding password hash) by username.
    Useful for populating session state after a successful login.
    """
    user_data = db.get_user_by_username(username)
    if user_data:
        user_data.pop("password_hash", None) # Ensure hash is removed
        return user_data
    return None