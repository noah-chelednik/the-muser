# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **GitHub:** Open a [private security advisory](https://github.com/noah-chelednik/the-muser/security/advisories/new)
2. **Expected response:** Within 72 hours

Please do **not** open a public GitHub issue for security vulnerabilities.

## Scope

In scope:
- LLM prompt injection that causes unintended tool execution
- Path traversal in tool parameters (e.g., reading/writing files outside compositions/)
- Subprocess injection via malformed tool arguments
- Credential exposure in logs or error messages

Out of scope:
- AI model output quality or bias
- Denial of service via large generation requests (local tool, user's own hardware)
- Issues in upstream model repositories (ACE-Step, NotaGen, etc.)
