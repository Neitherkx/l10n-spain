/** @odoo-module **/
/* Copyright 2026 Grupo Isonor - David Palanca
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

/* Three constraints shape this tour:
 *
 * - In manual mode every step must carry a `run`, otherwise the tour engine
 *   logs "Step ignored" and skips it. A purely informative pointer is
 *   therefore impossible: whatever it points at, the user has to click.
 * - The engine only looks for the next anchor when the DOM mutates. A notebook
 *   page is still faded in during the only mutations that follow the click on
 *   its tab, so an anchor placed inside the page that has just been opened
 *   never gets a pointer. Every step therefore points at something that is
 *   already laid out when the previous one is consumed.
 * - Odoo offers the tour on connection without redirecting anywhere, so it has
 *   to start on the apps screen and walk its way to the deliveries.
 *
 * Triggers rely on technical attributes only, never on translated labels. */
registry.category("web_tour.tours").add("l10n_es_deca_onboarding", {
  url: "/odoo",
  steps: () => [
    {
      /* The home action of the user is whatever they picked, so the only
       * anchor guaranteed to be on screen is the apps grid button. */
      trigger: ".o_grid_apps_menu__button",
      content: _t("Let us issue a DeCA from end to end. Open the apps menu."),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: ".o_app[data-menu-xmlid='stock.menu_stock_root']",
      content: _t("The DeCA lives in Inventory, next to the deliveries it covers."),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: "button[data-menu-xmlid='stock.menu_stock_warehouse_mgmt']",
      content: _t("Open the operations menu."),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: ".dropdown-item[data-menu-xmlid='stock.out_picking']",
      content: _t(
        "The document is only issued for deliveries: a receipt never " +
          "generates one."
      ),
      tooltipPosition: "right",
      run: "click",
    },
    {
      /* Anchored on a delivery whose DeCA badge is red, that is, one
       * with no document yet, so the rest of the tour finds editable
       * fields and the generate button. */
      trigger:
        ".o_list_view .o_data_row:has([name='deca_state'] .text-bg-danger) " +
        ".o_data_cell[name='name']",
      content: _t(
        "The DeCA column tells you at a glance which deliveries still have " +
          "no document. Open this one."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: ".o_form_view [name='deca_carrier_id'] input",
      content: _t(
        "Say who actually hauls the goods. The DeCA cannot be generated " +
          "without an effective carrier."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: "button[name='action_generate_deca']",
      content: _t(
        "Then generate the document from here. It is created in draft " +
          "state, so you can still review it."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: ".o_form_view .o_notebook .nav-link[name='vehicle']",
      content: _t(
        "This is the DeCA. Check the data on these tabs: the tractor plate " +
          "is the one piece the delivery cannot guess."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: "button[name='action_issue']",
      content: _t(
        "Issue it when everything is right. Odoo freezes the PDF, stamps " +
          "its SHA-256 fingerprint and publishes the link behind the QR code."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
    {
      trigger: ".o_form_view [name='public_url']",
      content: _t(
        "This is the address the QR code points at. The inspecting officer " +
          "opens it and downloads the document straight from there."
      ),
      tooltipPosition: "bottom",
      run: "click",
    },
  ],
});
