# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "DeCA Spain - Electronic Administrative Control Document",
    "summary": (
        "Generate, issue and keep the Electronic Administrative Control "
        "Document (DeCA) for road freight transport from Inventory deliveries"
    ),
    "author": "Grupo Isonor",
    "website": "https://github.com/OCA/l10n-spain",
    "license": "AGPL-3",
    "category": "Inventory/Delivery",
    "version": "18.0.1.1.0",
    "depends": ["stock", "mail", "web_tour"],
    "external_dependencies": {"python": ["qrcode", "reportlab", "PyPDF2"]},
    "data": [
        "security/deca_security.xml",
        "security/ir.model.access.csv",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
        "data/web_tour_data.xml",
        "wizards/deca_modify_wizard_views.xml",
        "wizards/deca_reissue_wizard_views.xml",
        "wizards/deca_cancel_wizard_views.xml",
        "wizards/deca_own_document_wizard_views.xml",
        "views/deca_vehicle_views.xml",
        "views/deca_document_views.xml",
        "views/stock_picking_views.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/deca_menus.xml",
        "report/deca_report.xml",
        "report/deca_report_templates.xml",
        "templates/deca_public_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "l10n_es_deca/static/src/scss/deca_qr_configure.scss",
            "l10n_es_deca/static/src/scss/deca_tour.scss",
            "l10n_es_deca/static/src/js/deca_qr_configure.esm.js",
            "l10n_es_deca/static/src/js/deca_qr_configure.xml",
            "l10n_es_deca/static/src/js/deca_tour.esm.js",
            "l10n_es_deca/static/src/js/deca_tour_launcher.esm.js",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
