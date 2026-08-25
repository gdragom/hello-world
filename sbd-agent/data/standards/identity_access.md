# Identity and Access Management Standard

## AUTH-01 Strong authentication
Applications must enforce multi-factor authentication for privileged and remote access.
Service accounts must use managed identities or short-lived credentials — no long-lived static keys in code.

## AUTH-02 Authorization
Enforce least privilege using role-based access control. Separate duties for production changes.
Deny by default for administrative APIs.

## AUTH-03 Session management
Sessions must expire, rotate tokens, and bind cookies with Secure and HttpOnly flags for web apps.
