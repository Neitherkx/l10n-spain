# Electronic Administrative Control Document (DeCA)

This module implements the **Electronic Administrative Control Document (DeCA)** for
road freight transport in Spain, in compliance with:

- Resolution of 5 June 2026 of the Directorate-General for Land Transport
  (BOE-A-2026-12784).
- Order FOM/2861/2012, of 13 December (article 6).
- Act 9/2025.

## Features

- Generates a DeCA out of one or several deliveries (`stock.picking`), without depending
  on any TMS module.
- Issuance with a **logically single-use public token**, public URL, QR code and
  **SHA-256** fingerprint of the PDF, so that the document can be shown on the road
  without manual interaction.
- **Method A** (_Register modification_, section Quinto.1): the new data is added to the
  same PDF, keeping token, URL and QR, with an immutable change history printed on the
  document itself.
- **Method B** (_Reissue DeCA_, section Quinto.2): generates a new document with its own
  token and redirects the old link to the one in force.
- **Cancellation**: voids a DeCA whose service never starts, keeping the PDF and the
  token due to the retention obligation.
- **Automatic closing of the public access** seven calendar days after the end of the
  service, and **access log** (date, IP, method and status code) with a scheduled purge.
- **Vehicle** master data (tractor and trailer plates) per carrier.
- Control of **receipts**: allows attaching the DeCA received from the supplier.
- **Your own document**: _Convert document to DeCA_ takes a PDF of your choice and
  stamps the DeCA QR code on it, dragging it over a preview of the page. The stamped
  file then replaces the document Odoo generates: it is the one carried in the vehicle,
  the one the authority downloads from the public link and the one the SHA-256
  fingerprint is computed over. A DeCA built this way does not need any delivery to be
  selected, because your own document already details the shipment.
- **Guided tour** of the whole flow, available at any time from _Inventory →
  Configuration → DeCA guided tour_.

## Configuration

In _Inventory → Configuration → Settings → DeCA_:

- **Own fleet**: the company is set as the effective carrier by default.
- **DeCA public domain**: leave it empty unless a reverse proxy publishes this company's
  documents under a different domain name. By default the instance's own domain
  (`web.base.url`) is used, which is what answers `/deca/<token>`. The company's
  commercial website is not used, because it usually does not serve that route and the
  QR would be broken.
- **Default QR placement on your own document**: starting page, position and size of the
  QR code when a customer converts their own document into a DeCA. It can still be
  dragged document by document.

Flag as **DeCA Carrier** the contacts providing the transport service and register their
plates in the _Vehicles_ tab.

## Known conflicts

The OCA module `web_no_bubble` hides every tour pointer with a
`.o_tour_pointer { display: none; }` rule. Since this module ships a guided tour, it
restores the pointer with a more specific selector. If `web_no_bubble` is installed, the
core Odoo onboarding pointers become visible again as a side effect.

Launching the guided tour turns on the onboarding of the current user
(`res.users.tour_enabled`), which is how Odoo allows a tour to be replayed. As a
consequence, once the DeCA tour ends Odoo chains the next pending onboarding tour of the
user, if there is one.

## Multi-company

- Each company only sees its own DeCA, lines, modifications and access records (global
  record rules).
- Plates can be assigned to a company or left blank to share them across all of them.
- Numbering is independent per company: the first time a company issues a DeCA its own
  `ir.sequence` is created automatically with the code `l10n.es.deca` and the prefix
  `DECA/%(year)s/`, which can be adjusted afterwards from _Technical settings →
  Sequences_.
- The **DeCA public domain** and the **Own fleet** option are configured per company.

## Dependencies

- Odoo: `stock`, `mail`, `web_tour`
- Python: `qrcode`, `reportlab`, `PyPDF2`
