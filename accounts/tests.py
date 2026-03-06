"""Tests for the accounts app."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class SignupViewTests(TestCase):
    """Test cases for user signup functionality."""

    def test_get_signup_page_returns_200(self):
        """Test that GET request to signup page returns 200."""
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_get_signup_page_renders_correct_template(self):
        """Test that signup page uses correct template."""
        response = self.client.get(reverse("signup"))
        self.assertTemplateUsed(response, "accounts/signup.html")

    def test_post_valid_signup_creates_user(self):
        """Test that valid POST creates a new user."""
        user_data = {
            "username": "newuser",
            "password1": "testpass123!@#",
            "password2": "testpass123!@#",
        }
        response = self.client.post(reverse("signup"), user_data)

        # Check user was created
        self.assertTrue(User.objects.filter(username="newuser").exists())

        # Check redirect to home
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_post_valid_signup_logs_in_user(self):
        """Test that successful signup automatically logs in the user."""
        user_data = {
            "username": "autouser",
            "password1": "testpass123!@#",
            "password2": "testpass123!@#",
        }
        self.client.post(reverse("signup"), user_data)

        # Check user is authenticated
        user = User.objects.get(username="autouser")
        self.assertTrue(user.is_authenticated)

    def test_post_invalid_signup_rerenders_form(self):
        """Test that invalid POST rerenders the form with errors."""
        user_data = {
            "username": "baduser",
            "password1": "pass123",
            "password2": "different",  # Passwords don't match
        }
        response = self.client.post(reverse("signup"), user_data)

        # Should not create user
        self.assertFalse(User.objects.filter(username="baduser").exists())

        # Should return 200 and display form again
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_post_missing_fields_shows_errors(self):
        """Test that missing required fields shows validation errors."""
        user_data = {
            "username": "",
            "password1": "",
            "password2": "",
        }
        response = self.client.post(reverse("signup"), user_data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "username", "This field is required.")

    def test_post_duplicate_username_shows_error(self):
        """Test that duplicate username shows validation error."""
        # Create existing user
        User.objects.create_user(username="existing", password="pass123")

        # Try to create another user with same username
        user_data = {
            "username": "existing",
            "password1": "testpass123!@#",
            "password2": "testpass123!@#",
        }
        response = self.client.post(reverse("signup"), user_data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        # Should only have one user with this username
        self.assertEqual(User.objects.filter(username="existing").count(), 1)

    def test_post_short_password_shows_error(self):
        """Test that too-short password shows validation error."""
        user_data = {
            "username": "shortpass",
            "password1": "123",  # Too short
            "password2": "123",
        }
        response = self.client.post(reverse("signup"), user_data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="shortpass").exists())
