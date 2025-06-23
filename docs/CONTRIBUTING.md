# List-IQ Contribution Guide

We are thrilled that you are considering contributing to List-IQ! This document provides guidelines for contributing to the project.

## Contribution Process

1.  **Fork** the repository on GitHub
2.  **Clone** your fork locally
3.  **Create a branch** for your changes
4.  **Make your changes**, following the coding conventions
5.  **Test** your changes
6.  **Submit** a pull request

## Development Environment

### Prerequisites

-   Docker and Docker Compose
-   Python 3.8 or higher
-   Git

### Development Setup

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-organization/list-iq.git
    cd list-iq
    ```

2.  Create a `.env` file from the template:
    ```bash
    cp config/.env.example .env
    ```

3.  Start the application in development mode:
    ```bash
    docker-compose -f config/docker-compose.dev.yml up -d
    ```

## Project Structure

-   `app/`: Application source code
    -   `models/`: Data models
    -   `routes/`: Routes and controllers
    -   `templates/`: Jinja2 templates
    -   `static/`: Static files
    -   `translations/`: Translation files
-   `config/`: Configuration files
-   `docs/`: Documentation
-   `scripts/`: Utility scripts

## Coding Conventions

### Python

-   Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
-   Use docstrings to document functions and classes
-   Write unit tests for new features

### JavaScript

-   Follow ESLint conventions
-   Use comments to explain complex code
-   Prefer arrow functions and ES6+ methods

### HTML/CSS

-   Use semantic classes
-   Follow BEM conventions for CSS class naming
-   Ensure the code is responsive

## Translations

To add or modify translations:

1.  Modify the `.po` files in the `translations/` directory
2.  Compile the `.po` files into `.mo` files:
    ```bash
    pybabel compile -d translations
    ```

## Testing

Run the tests before submitting a pull request:

```bash
# Unit tests
pytest app/tests

# Integration tests
pytest app/tests/integration

Submitting Pull Requests

Ensure your code adheres to the coding conventions

Include tests for new features

Update the documentation if necessary

Clearly describe the changes made

Reporting Bugs

If you find a bug, please create an issue on GitHub with:

A clear description of the problem

The steps to reproduce the bug

The expected behavior

Screenshots if possible

Your environment (OS, browser, List-IQ version)

Feature Requests

To propose a new feature:

Clearly describe the feature

Explain why this feature would be useful

Suggest an implementation approach if possible

License

By contributing to List-IQ, you agree that your contributions will be licensed under the same license as the project (see the LICENSE file).

Generated code
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END