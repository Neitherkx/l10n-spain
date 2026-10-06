# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo import http
from odoo.http import request


class DecaPublicController(http.Controller):
    """Public download of the DeCA (section Tercero of the Resolution).

    The link points directly to the PDF binary: no login, no intermediate page
    and no manual interaction at all.
    """

    @staticmethod
    def _client_info():
        headers = request.httprequest.headers
        return {
            "ip": request.httprequest.remote_addr,
            "method": request.httprequest.method,
            "user_agent": headers.get("User-Agent", ""),
        }

    def _render_notice(self, deca, template, status, **values):
        info = self._client_info()
        deca._log_public_access(info["ip"], info["method"], status, info["user_agent"])
        return request.render(template, dict(values, deca=deca), status=status)

    @http.route(
        "/deca/<string:token>",
        type="http",
        auth="public",
        methods=["GET", "HEAD"],
        csrf=False,
        sitemap=False,
    )
    def download_deca(self, token, **kwargs):
        deca = (
            request.env["l10n.es.deca"].sudo().search([("token", "=", token)], limit=1)
        )
        if not deca or deca.state == "draft":
            return request.not_found()

        if deca.state == "cancelled":
            return self._render_notice(deca, "l10n_es_deca.deca_public_cancelled", 410)
        if deca.state == "replaced":
            replacement = deca.replacement_deca_id
            return self._render_notice(
                deca,
                "l10n_es_deca.deca_public_replaced",
                410,
                replacement=replacement,
            )
        if deca.state == "closed" or not deca._is_public_access_open():
            return self._render_notice(deca, "l10n_es_deca.deca_public_closed", 410)

        pdf = base64.b64decode(deca.pdf_attachment_id.sudo().datas or b"")
        info = self._client_info()
        deca._log_public_access(info["ip"], info["method"], 200, info["user_agent"])
        filename = f"{deca.name.replace('/', '_')}.pdf"
        return request.make_response(
            pdf,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf))),
                ("Content-Disposition", f'inline; filename="{filename}"'),
                ("X-Content-Type-Options", "nosniff"),
                ("Cache-Control", "no-store"),
            ],
        )
