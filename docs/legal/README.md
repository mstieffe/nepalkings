# Legal and Policy Documents

These documents are published by the production API under `/legal` and linked
from account registration and Settings.

- [Terms of Service](TERMS.md)
- [Privacy Policy](PRIVACY.md)
- [Community Guidelines](COMMUNITY_GUIDELINES.md)
- [Attribution and third-party notices](ATTRIBUTION.md)

When Terms or Privacy wording changes materially:

1. update the document;
2. update `LEGAL_TERMS_VERSION` or `LEGAL_PRIVACY_VERSION` in the release
   configuration and examples;
3. run legal-route and registration tests;
4. deploy and verify `/legal/versions` before opening registration;
5. document whether existing users must acknowledge the new version.

Do not add private operator data or a personal address casually. The optional
post-launch legal review and branded contact work is tracked in
[the launch follow-up backlog](../plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md#legal-and-policy-follow-up).
