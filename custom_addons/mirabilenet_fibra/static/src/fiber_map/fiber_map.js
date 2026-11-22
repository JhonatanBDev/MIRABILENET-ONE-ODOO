/* global L */
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const DEFAULT_CENTER = [-17.4, -63.88];
const LABEL_MIN_ZOOM = 16;
const ESRI_URL =
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
// Esri no tiene fotos de Yapacaní más allá del zoom 17: desde el 18 devuelve una imagen gris
// «Map data not yet available». Se piden las del 17 y Leaflet las agranda al acercarse.
const ESRI_MAX_NATIVE_ZOOM = 17;

export const NAP_STATUS = [
    { key: "libre", label: _t("Con puertos libres") },
    { key: "casi_llena", label: _t("Casi llena") },
    { key: "llena", label: _t("Llena") },
    { key: "danada", label: _t("Dañada") },
    { key: "sin_datos", label: _t("Por verificar o sin puertos") },
];

/** Elemento DOM con texto (sin HTML: los datos vienen de la base). */
function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    if (text !== undefined && text !== null) {
        node.textContent = String(text);
    }
    return node;
}

function row(parent, label, value) {
    const line = el("div", "o_fiber_popup_row");
    line.appendChild(el("span", "o_fiber_popup_label", label + ": "));
    line.appendChild(el("span", "", value));
    parent.appendChild(line);
}

export class FiberMap extends Component {
    static template = "mirabilenet_fibra.FiberMap";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.napStatus = NAP_STATUS;
        this.state = useState({
            loaded: false,
            branch: "",
            napState: "",
            segmentType: "",
            onlyFree: false,
            showCustomers: true,
            search: "",
            warningsOpen: false,
            warningsDismissed: false,
            data: { naps: [], segments: [], customers: [], warnings: [] },
        });
        onWillStart(async () => {
            this.state.data = await this.orm.call(
                "mirabilenet.fiber.nap",
                "get_fiber_map_data",
                []
            );
            this.state.loaded = true;
        });
        onMounted(() => this.setupMap());
        onWillUnmount(() => {
            if (this.resizeObserver) {
                this.resizeObserver.disconnect();
            }
            if (this.map) {
                this.map.remove();
            }
        });
    }

    // ------------------------------------------------------------------
    // Datos derivados para la plantilla
    // ------------------------------------------------------------------
    get branches() {
        const names = new Set();
        for (const nap of this.state.data.naps) {
            if (nap.branch_line) {
                names.add(nap.branch_line);
            }
        }
        for (const segment of this.state.data.segments) {
            if (segment.branch_line) {
                names.add(segment.branch_line);
            }
        }
        return [...names].sort((a, b) => a.localeCompare(b));
    }

    get legendLines() {
        const seen = new Map();
        for (const segment of this.state.data.segments) {
            const key =
                segment.type === "troncal" || segment.type === "alimentador"
                    ? segment.type_label
                    : segment.branch_line || segment.code;
            if (!seen.has(key)) {
                seen.set(key, { label: key, color: segment.color, type: segment.type });
            }
        }
        return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label));
    }

    get warnings() {
        return this.state.data.warnings || [];
    }

    get canMove() {
        return Boolean(this.state.data.can_move);
    }

    // ------------------------------------------------------------------
    // Mapa
    // ------------------------------------------------------------------
    setupMap() {
        const map = L.map(this.mapRef.el, { zoomControl: true, maxZoom: 20 });
        this.map = map;
        const satellite = L.tileLayer(ESRI_URL, {
            maxZoom: 20,
            maxNativeZoom: ESRI_MAX_NATIVE_ZOOM,
            attribution: "Esri World Imagery",
        });
        const osm = L.tileLayer(OSM_URL, {
            maxZoom: 20,
            maxNativeZoom: 19,
            attribution: "&copy; OpenStreetMap",
        });
        satellite.addTo(map);
        // Las líneas en su propio panel, debajo de los marcadores.
        map.createPane("fiberLines").style.zIndex = 450;
        this.segmentLayer = L.layerGroup().addTo(map);
        this.customerLayer = L.layerGroup().addTo(map);
        this.napLayer = L.layerGroup().addTo(map);
        L.control
            .layers(
                { [_t("Satélite")]: satellite, [_t("OpenStreetMap")]: osm },
                {},
                { position: "topright" }
            )
            .addTo(map);
        L.control.scale({ imperial: false }).addTo(map);
        map.on("zoomend moveend", () => this.updateLabels());
        this.resizeObserver = new ResizeObserver(() => map.invalidateSize());
        this.resizeObserver.observe(this.mapRef.el);
        this.render_layers();
        this.initialView();
    }

    initialView() {
        const params = this.props.action.params || {};
        const context = this.props.action.context || {};
        const napId = params.nap_id || context.mirabilenet_fiber_nap_id;
        const segmentId = params.segment_id;
        if (napId && this.focus("nap", napId, false)) {
            return;
        }
        if (segmentId && this.focus("segment", segmentId, false)) {
            return;
        }
        this.fitAll();
    }

    fitAll() {
        const points = [];
        for (const nap of this.state.data.naps) {
            points.push([nap.lat, nap.lon]);
        }
        for (const segment of this.state.data.segments) {
            points.push(...segment.points);
        }
        if (points.length) {
            this.map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 17 });
        } else {
            this.map.setView(DEFAULT_CENTER, 14);
        }
    }

    napVisible(nap) {
        const s = this.state;
        return (
            (!s.branch || nap.branch_line === s.branch) &&
            (!s.napState || nap.state === s.napState) &&
            (!s.onlyFree || nap.ports_free > 0)
        );
    }

    segmentVisible(segment) {
        const s = this.state;
        return (
            (!s.branch || segment.branch_line === s.branch) &&
            (!s.segmentType || segment.type === s.segmentType)
        );
    }

    render_layers() {
        if (!this.map) {
            return;
        }
        this.segmentLayer.clearLayers();
        this.napLayer.clearLayers();
        this.customerLayer.clearLayers();
        this.napMarkers = new Map();
        this.segmentLines = new Map();
        this.customerMarkers = new Map();
        const visibleNaps = new Set();
        for (const segment of this.state.data.segments) {
            if (!this.segmentVisible(segment)) {
                continue;
            }
            const line = L.polyline(segment.points, {
                pane: "fiberLines",
                color: segment.color,
                weight: segment.type === "troncal" ? 6 : 5,
                opacity: 0.9,
                dashArray: segment.dashed ? "10 8" : null,
            });
            line.bindPopup(() => this.segmentPopup(segment));
            line.addTo(this.segmentLayer);
            this.segmentLines.set(segment.id, line);
        }
        for (const nap of this.state.data.naps) {
            if (!this.napVisible(nap)) {
                continue;
            }
            visibleNaps.add(nap.id);
            const marker = L.marker([nap.lat, nap.lon], {
                icon: L.divIcon({
                    className: "o_fiber_nap_icon",
                    html: `<div class="o_fiber_nap_square o_fiber_status_${nap.status}"></div>`,
                    iconSize: [20, 20],
                    iconAnchor: [10, 10],
                    popupAnchor: [0, -10],
                }),
                draggable: this.canMove,
                title: `${nap.code}${nap.branch_line ? " · " + nap.branch_line : ""}`,
                riseOnHover: true,
            });
            marker.bindTooltip(nap.name || nap.code, {
                permanent: true,
                direction: "right",
                offset: [12, 0],
                className: "o_fiber_nap_label",
            });
            marker.bindPopup(() => this.napPopup(nap));
            if (this.canMove) {
                marker.on("dragend", () => this.saveMarker(nap, marker));
            }
            marker.addTo(this.napLayer);
            this.napMarkers.set(nap.id, marker);
        }
        if (this.state.showCustomers) {
            for (const customer of this.state.data.customers) {
                if (!visibleNaps.has(customer.nap_id)) {
                    continue;
                }
                const marker = L.marker([customer.lat, customer.lon], {
                    icon: L.divIcon({
                        className: "o_fiber_customer_icon",
                        html: '<div class="o_fiber_customer_dot"></div>',
                        iconSize: [14, 14],
                        iconAnchor: [7, 7],
                    }),
                    title: customer.name,
                });
                marker.bindPopup(() => this.customerPopup(customer));
                marker.addTo(this.customerLayer);
                this.customerMarkers.set(customer.service_id, marker);
            }
        }
        this.updateLabels();
    }

    /** Etiquetas desde el zoom 16, con un anti-solapamiento sencillo. */
    updateLabels() {
        if (!this.map) {
            return;
        }
        const container = this.map.getContainer();
        const show = this.map.getZoom() >= LABEL_MIN_ZOOM;
        container.classList.toggle("o_fiber_labels_on", show);
        const labels = container.querySelectorAll(".o_fiber_nap_label");
        labels.forEach((label) => label.classList.remove("o_fiber_label_hidden"));
        if (!show) {
            return;
        }
        const taken = [];
        labels.forEach((label) => {
            const box = label.getBoundingClientRect();
            const overlaps = taken.some(
                (b) =>
                    box.left < b.right &&
                    box.right > b.left &&
                    box.top < b.bottom &&
                    box.bottom > b.top
            );
            if (overlaps) {
                label.classList.add("o_fiber_label_hidden");
            } else {
                taken.push(box);
            }
        });
    }

    // ------------------------------------------------------------------
    // Ventanas emergentes
    // ------------------------------------------------------------------
    napPopup(nap) {
        const box = el("div", "o_fiber_popup");
        box.appendChild(el("div", "o_fiber_popup_title", nap.code));
        row(box, _t("Nombre"), nap.name || "-");
        row(box, _t("Ramal"), nap.branch_line || "-");
        row(box, _t("Estado"), nap.state_label);
        row(
            box,
            _t("Puertos libres"),
            nap.port_count ? `${nap.ports_free} / ${nap.port_count}` : _t("sin definir")
        );
        const button = el("button", "btn btn-primary btn-sm mt-2", _t("Abrir NAP"));
        button.addEventListener("click", () => this.openRecord("mirabilenet.fiber.nap", nap.id));
        box.appendChild(button);
        return box;
    }

    segmentPopup(segment) {
        const box = el("div", "o_fiber_popup");
        box.appendChild(el("div", "o_fiber_popup_title", segment.code));
        row(box, _t("Nombre"), segment.name || "-");
        row(box, _t("Tipo"), segment.type_label);
        row(box, _t("Longitud"), segment.length_m ? `${segment.length_m} m` : "-");
        row(box, _t("Estado"), segment.state_label);
        row(box, _t("NAP en ruta"), segment.naps.join(" → ") || "-");
        if (segment.dashed) {
            box.appendChild(el("div", "text-warning", _t("Sin recorrido real: línea recta.")));
        }
        const button = el("button", "btn btn-primary btn-sm mt-2", _t("Abrir tramo"));
        button.addEventListener("click", () =>
            this.openRecord("mirabilenet.fiber.segment", segment.id)
        );
        box.appendChild(button);
        return box;
    }

    customerPopup(customer) {
        const box = el("div", "o_fiber_popup");
        box.appendChild(el("div", "o_fiber_popup_title", customer.name));
        row(box, _t("Teléfono"), customer.phone || "-");
        row(box, _t("NAP"), customer.nap_code);
        row(box, _t("Puerto"), customer.port);
        const button = el("button", "btn btn-primary btn-sm mt-2", _t("Abrir servicio"));
        button.addEventListener("click", () =>
            this.openRecord("mirabilenet.service", customer.service_id)
        );
        box.appendChild(button);
        return box;
    }

    openRecord(resModel, resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async saveMarker(nap, marker) {
        const position = marker.getLatLng();
        try {
            await this.orm.call("mirabilenet.fiber.nap", "move_nap_marker", [
                nap.id,
                position.lat,
                position.lng,
            ]);
            nap.lat = position.lat;
            nap.lon = position.lng;
            this.notification.add(_t("Ubicación de %s guardada.", nap.code), {
                type: "success",
            });
        } catch (error) {
            marker.setLatLng([nap.lat, nap.lon]);
            throw error;
        }
    }

    // ------------------------------------------------------------------
    // Interacción
    // ------------------------------------------------------------------
    setFilter(name, value) {
        this.state[name] = value;
        this.render_layers();
    }

    onToggleCustomers(ev) {
        this.state.showCustomers = ev.target.checked;
        this.render_layers();
    }

    resetFilters() {
        Object.assign(this.state, { branch: "", napState: "", segmentType: "", onlyFree: false });
        this.render_layers();
    }

    /** Centra el mapa en una NAP o un tramo y abre su ventana. */
    focus(model, id, animate = true) {
        const find = () => (model === "nap" ? this.napMarkers : this.segmentLines).get(id);
        let layer = find();
        if (!layer) {
            this.resetFilters();
            layer = find();
        }
        if (!layer) {
            const nap = this.state.data.naps.find((n) => n.id === id);
            if (model === "nap" && !nap) {
                this.notification.add(_t("Esa NAP no tiene coordenadas."), { type: "warning" });
            }
            return false;
        }
        if (model === "nap") {
            const target = layer.getLatLng();
            if (animate) {
                this.map.flyTo(target, 18, { duration: 0.8 });
                this.map.once("moveend", () => layer.openPopup());
            } else {
                this.map.setView(target, 18);
                layer.openPopup();
            }
        } else {
            this.map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 18 });
            layer.openPopup(layer.getCenter());
        }
        return true;
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            this.search();
        }
    }

    search() {
        const term = (this.state.search || "").trim().toLowerCase();
        if (!term) {
            return;
        }
        const nap =
            this.state.data.naps.find((n) => n.code.toLowerCase() === term) ||
            this.state.data.naps.find(
                (n) => n.code.toLowerCase().includes(term) || n.name.toLowerCase() === term
            );
        if (nap) {
            this.focus("nap", nap.id);
            return;
        }
        const customer = this.state.data.customers.find((c) =>
            c.name.toLowerCase().includes(term)
        );
        if (customer) {
            if (!this.state.showCustomers) {
                this.state.showCustomers = true;
            }
            this.resetFilters();
            const marker = this.customerMarkers.get(customer.service_id);
            if (marker) {
                this.map.flyTo(marker.getLatLng(), 18, { duration: 0.8 });
                this.map.once("moveend", () => marker.openPopup());
                return;
            }
        }
        this.notification.add(_t("No se encontró «%s».", this.state.search), {
            type: "warning",
        });
    }

    toggleWarnings() {
        this.state.warningsOpen = !this.state.warningsOpen;
    }

    dismissWarnings() {
        this.state.warningsDismissed = true;
    }

    onWarningClick(warning) {
        this.focus(warning.model, warning.id);
    }
}

registry.category("actions").add("mirabilenet_fibra.fiber_map", FiberMap);
