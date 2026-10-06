/** @odoo-module **/
/* Copyright 2026 Grupo Isonor - David Palanca
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {
  Component,
  onMounted,
  onWillStart,
  onWillUnmount,
  useRef,
  useState,
} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

const MIN_SIZE = 1;
const MAX_SIZE = 50;

export class DecaQrConfigure extends Component {
  static template = "l10n_es_deca.DecaQrConfigure";
  static props = {
    action: {type: Object, optional: true},
    actionId: {type: [Number, Boolean], optional: true},
    className: {type: String, optional: true},
    updateActionState: {type: Function, optional: true},
  };

  setup() {
    const params = this.props.action.params || {};
    this.resModel = params.res_model || "l10n.es.deca";
    this.resId = params.res_id;
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.iframe = useRef("iframe");
    this.state = useState({
      name: "",
      editable: false,
      pageCount: 0,
      page: 1,
      positionX: 0,
      positionY: 0,
      size: 0,
      dirty: false,
      ready: false,
    });
    this.viewerUrl =
      "/web/static/lib/pdfjs/web/viewer.html?file=" +
      encodeURIComponent(`/web/content/${this.resModel}/${this.resId}/custom_pdf`);

    onWillStart(async () => {
      const info = await this.orm.call(this.resModel, "get_qr_placement_info", [
        [this.resId],
      ]);
      Object.assign(this.state, {
        name: info.name,
        editable: info.editable,
        pageCount: info.page_count,
        page: info.page || 1,
        positionX: info.position_x,
        positionY: info.position_y,
        size: info.size,
      });
    });
    onMounted(() => this._waitForViewer());
    onWillUnmount(() => {
      clearTimeout(this.pollTimeout);
      this._unbindMove();
    });
  }

  // ------------------------------------------------------------------
  // pdf.js viewer plumbing
  // ------------------------------------------------------------------
  get _iframeDoc() {
    return this.iframe.el && this.iframe.el.contentDocument;
  }

  _waitForViewer() {
    const doc = this._iframeDoc;
    const pages = doc && doc.getElementsByClassName("page");
    if (pages && pages.length && doc.getElementsByClassName("endOfContent").length) {
      this.state.ready = true;
      this._renderMarker();
      // Pdf.js re-creates pages while scrolling or zooming.
      this.pollTimeout = setTimeout(() => this._keepMarkerAlive(), 500);
      return;
    }
    this.pollTimeout = setTimeout(() => this._waitForViewer(), 100);
  }

  _keepMarkerAlive() {
    const doc = this._iframeDoc;
    if (doc && !doc.querySelector(".o_deca_qr_marker")) {
      this._renderMarker();
    }
    this.pollTimeout = setTimeout(() => this._keepMarkerAlive(), 500);
  }

  _getPageEl(pageNumber) {
    const doc = this._iframeDoc;
    if (!doc) {
      return null;
    }
    return doc.getElementsByClassName("page")[pageNumber - 1] || null;
  }

  /**
   * The QR is square in the final PDF, so its height as a percentage of the
   * page depends on the page aspect ratio.
   *
   * @param {Element} pageEl - the PDF page element
   * @returns {Number} the QR height as a percentage of the page height
   */
  _heightPercent(pageEl) {
    const box = pageEl.getBoundingClientRect();
    return box.height ? (this.state.size * box.width) / box.height : this.state.size;
  }

  _renderMarker() {
    const doc = this._iframeDoc;
    if (!doc) {
      return;
    }
    for (const old of doc.querySelectorAll(".o_deca_qr_marker")) {
      old.remove();
    }
    const pageEl = this._getPageEl(this.state.page);
    if (!pageEl) {
      return;
    }
    const marker = doc.createElement("div");
    marker.className = "o_deca_qr_marker";
    // Styles are inline: this node lives inside the pdf.js iframe, which
    // does not load the backend asset bundle.
    Object.assign(marker.style, {
      position: "absolute",
      boxSizing: "border-box",
      border: "2px dashed #017e84",
      background: "rgba(1, 126, 132, 0.25)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: "100",
      cursor: this.state.editable ? "move" : "not-allowed",
      userSelect: "none",
    });
    marker.style.left = `${this.state.positionX}%`;
    marker.style.top = `${this.state.positionY}%`;
    marker.style.width = `${this.state.size}%`;
    marker.style.height = `${this._heightPercent(pageEl)}%`;

    const label = doc.createElement("span");
    label.textContent = "QR";
    Object.assign(label.style, {
      fontWeight: "bold",
      color: "#017e84",
      pointerEvents: "none",
    });
    marker.appendChild(label);

    if (this.state.editable) {
      const handle = doc.createElement("span");
      handle.className = "o_deca_qr_resize";
      Object.assign(handle.style, {
        position: "absolute",
        right: "-5px",
        bottom: "-5px",
        width: "12px",
        height: "12px",
        background: "#017e84",
        borderRadius: "2px",
        cursor: "se-resize",
      });
      marker.appendChild(handle);
      marker.addEventListener("mousedown", (ev) => this._onMarkerDown(ev));
    }
    pageEl.appendChild(marker);
    this.marker = marker;
  }

  // ------------------------------------------------------------------
  // Drag & resize
  // ------------------------------------------------------------------
  _onMarkerDown(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const pageEl = this._getPageEl(this.state.page);
    if (!pageEl) {
      return;
    }
    const box = pageEl.getBoundingClientRect();
    this.drag = {
      pageEl,
      box,
      resizing: ev.target.classList.contains("o_deca_qr_resize"),
      startX: ev.clientX,
      originX: this.state.positionX,
      originY: this.state.positionY,
      originSize: this.state.size,
      grabX: ev.clientX - box.left - (this.state.positionX / 100) * box.width,
      grabY: ev.clientY - box.top - (this.state.positionY / 100) * box.height,
    };
    this._moveHandler = (moveEv) => this._onMarkerMove(moveEv);
    this._upHandler = () => this._onMarkerUp();
    const doc = this._iframeDoc;
    doc.addEventListener("mousemove", this._moveHandler);
    doc.addEventListener("mouseup", this._upHandler);
  }

  _onMarkerMove(ev) {
    if (!this.drag) {
      return;
    }
    const {box, resizing} = this.drag;
    if (resizing) {
      const delta = ((ev.clientX - this.drag.startX) / box.width) * 100;
      this.state.size = this._clamp(this.drag.originSize + delta, MIN_SIZE, MAX_SIZE);
    } else {
      const heightPct = this._heightPercent(this.drag.pageEl);
      this.state.positionX = this._clamp(
        ((ev.clientX - box.left - this.drag.grabX) / box.width) * 100,
        0,
        100 - this.state.size
      );
      this.state.positionY = this._clamp(
        ((ev.clientY - box.top - this.drag.grabY) / box.height) * 100,
        0,
        100 - heightPct
      );
    }
    this.state.dirty = true;
    this._applyMarkerStyle();
  }

  _applyMarkerStyle() {
    if (!this.marker) {
      return;
    }
    this.marker.style.left = `${this.state.positionX}%`;
    this.marker.style.top = `${this.state.positionY}%`;
    this.marker.style.width = `${this.state.size}%`;
    this.marker.style.height = `${this._heightPercent(this.drag.pageEl)}%`;
  }

  _onMarkerUp() {
    this._unbindMove();
    this.drag = null;
  }

  _unbindMove() {
    const doc = this._iframeDoc;
    if (doc && this._moveHandler) {
      doc.removeEventListener("mousemove", this._moveHandler);
      doc.removeEventListener("mouseup", this._upHandler);
    }
    this._moveHandler = null;
    this._upHandler = null;
  }

  _clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
  }

  // ------------------------------------------------------------------
  // Toolbar
  // ------------------------------------------------------------------
  onPageChange(ev) {
    const page = this._clamp(
      parseInt(ev.target.value, 10) || 1,
      1,
      this.state.pageCount || 1
    );
    this.state.page = page;
    this.state.dirty = true;
    this._renderMarker();
  }

  onSizeChange(ev) {
    this.state.size = this._clamp(
      parseFloat(ev.target.value) || MIN_SIZE,
      MIN_SIZE,
      MAX_SIZE
    );
    this.state.dirty = true;
    this._renderMarker();
  }

  async onSave() {
    await this.orm.call(this.resModel, "set_qr_placement", [
      [this.resId],
      {
        page: this.state.page,
        position_x: this.state.positionX,
        position_y: this.state.positionY,
        size: this.state.size,
      },
    ]);
    this.state.dirty = false;
    this.notification.add(_t("QR position saved."), {type: "success"});
  }
}

registry.category("actions").add("l10n_es_deca_qr_configure", DecaQrConfigure);
