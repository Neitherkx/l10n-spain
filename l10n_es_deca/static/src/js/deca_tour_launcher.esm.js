/** @odoo-module **/

import {Component, onWillStart, xml} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/* The menu entry has to replay the tour on demand, which rules out the two
 * mechanisms `web_tour` offers out of the box:
 * - the automatic offer only fires for users whose `tour_enabled` is set, and
 *   that flag is computed to `False` as soon as the database has demo data or
 *   the user is not an administrator;
 * - the `?tour=` URL parameter starts the tour straight from the database, so
 *   it never redirects to the starting screen and it duplicates the pointer
 *   when the same tour is still pending.
 * Calling the service with the tour taken from the JS registry avoids both: it
 * enables the tours for the user, redirects to `/odoo/deliveries` and plays the
 * guide again even if it had already been consumed. */
export class DecaStartTour extends Component {
  static template = xml`<div class="o_deca_start_tour" />`;
  static props = ["*"];

  setup() {
    const tourService = useService("tour_service");
    onWillStart(() =>
      tourService.startTour("l10n_es_deca_onboarding", {mode: "manual"})
    );
  }
}

registry.category("actions").add("l10n_es_deca_start_tour", DecaStartTour);
