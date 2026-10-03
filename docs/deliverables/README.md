# Final report and presentation

Created at the user's explicit request after Phase 14 on 3 October 2026.

- `CartPilot_Final_Report.docx`: editable report, 18 numbered sections, exact algorithm/API appendices and 11 real browser figures.
- `CartPilot_Final_Report.pdf`: 18-page export of the same report content.
- `CartPilot_Final_Presentation.pptx`: 12 widescreen slides with real screenshots and speaker notes.

Student/team, institution, department, guide and submission date are clearly marked placeholders. Complete them and apply institution-required formatting before submission. This is a technical report draft; no institutional certificate, signature or peer-reviewed literature survey is fabricated. Original screenshots document the previously verified walkthrough, rather than a new live Shopify experiment.

Generation uses a temporary tool environment, not backend/frontend runtime dependencies:

```bash
python3 -m venv /tmp/cartpilot-document-tools
/tmp/cartpilot-document-tools/bin/pip install python-docx python-pptx reportlab
/tmp/cartpilot-document-tools/bin/python scripts/generate_academic_documents.py
```

Verified: DOCX/PPTX archive integrity, 12-slide count, shape bounds, report evidence claims, 18 PDF pages, PDF text/rendering and a representative report page. A full PowerPoint/Keynote rendering rehearsal remains advisable; native slide rendering was not run.

The local demo frontend is http://127.0.0.1:5174/dashboard while the started processes remain running. Select **Four-product Demo**. API documentation: http://127.0.0.1:8012/docs. A fresh disposable database preserves the original fixture; no approved actions were executed during this continuation.

Cloud deployment requires a selected hosting target and account access. See `../DEPLOYMENT_HANDOFF.md`. Generated files are included in the refreshed source submission ZIP.
