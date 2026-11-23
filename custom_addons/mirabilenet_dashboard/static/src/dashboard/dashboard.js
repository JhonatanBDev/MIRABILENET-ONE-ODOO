/* global Chart */
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const REFRESH_MS = 60000;
const PERIODS = [
    { key: "hoy", label: _t("Hoy") },
    { key: "7", label: _t("7 días") },
    { key: "30", label: _t("30 días") },
    { key: "90", label: _t("90 días") },
    { key: "mes", label: _t("Este mes") },
    { key: "mes_anterior", label: _t("Mes pasado") },
    { key: "rango", label: _t("Fechas…") },
];
const SECTION_LABELS = {
    alertas: _t("Alertas"),
    resumen: _t("Resumen"),
    negocio: _t("Negocio"),
    flujo: _t("Ingresos y servicios"),
    inicio: _t("Actividad y puesta en marcha"),
    cobranza: _t("Cobranza"),
    operacion: _t("Clientes, cobros y red"),
    cartera: _t("Cartera y pagos"),
    capacidad: _t("Capacidad y soporte"),
};
const SHORTCUTS = [
    { label: _t("Clientes"), icon: "fa-users", xmlid: "mirabilenet_isp.action_mirabilenet_customer" },
    { label: _t("Contratos"), icon: "fa-file-text-o", xmlid: "contract.action_customer_contract" },
    { label: _t("Pagos"), icon: "fa-money", xmlid: "account.action_account_payments" },
    { label: _t("Routers"), icon: "fa-server", xmlid: "mirabilenet_isp.action_mirabilenet_router" },
    { label: _t("Planes"), icon: "fa-tags", xmlid: "mirabilenet_isp.action_mirabilenet_plan" },
    { label: _t("Mapa de fibra"), icon: "fa-map-o", xmlid: "mirabilenet_fibra.action_mirabilenet_fiber_map" },
    { label: _t("Auditoría"), icon: "fa-history", xmlid: "mirabilenet_base.action_mirabilenet_audit_log" },
];
// Color de cada estado del servicio (variables de Odoo 19: siguen el modo oscuro).
const STATE_COLORS = {
    pendiente_instalacion: ["--info", "#17a2b8"],
    activo: ["--success", "#28a745"],
    moroso: ["--warning", "#ffc107"],
    suspendido: ["--orange", "#fd7e14"],
    baja: ["--secondary", "#6c757d"],
};
const PALETTE = [
    ["--primary", "#714b67"],
    ["--success", "#28a745"],
    ["--info", "#17a2b8"],
    ["--warning", "#ffc107"],
    ["--danger", "#dc3545"],
];
const FILTER_KEYS = ["region_id", "zone_id", "node_id", "plan_id", "payment_mode", "service_state"];
const ID_FILTERS = ["region_id", "zone_id", "node_id", "plan_id"];
const MONEY = new Intl.NumberFormat("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const INTEGER = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 1 });

function cssColor(variable, fallback) {
    // Odoo define las variables de color en el body (y las cambia en modo oscuro).
    for (const node of [document.body, document.documentElement]) {
        const value = getComputedStyle(node).getPropertyValue(variable).trim();
        if (value) {
            return value;
        }
    }
    return fallback;
}

export class MirabilenetDashboard extends Component {
    static template = "mirabilenet_dashboard.Dashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.periods = PERIODS;
        this.shortcuts = SHORTCUTS;
        this.sectionLabels = SECTION_LABELS;
        this.refs = {
            income: useRef("incomeChart"),
            states: useRef("statesChart"),
            daily: useRef("dailyChart"),
            methods: useRef("methodsChart"),
            movements: useRef("movementsChart"),
        };
        this.charts = {};
        this.state = useState({
            data: null,
            options: null,
            filters: { period: "30" },
            hidden: [],
            customizing: false,
            showFilters: false,
            loading: false,
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            const options = await this.orm.call("mirabilenet.dashboard", "get_filter_options", []);
            this.state.options = options;
            const prefs = options.preferencias || {};
            this.state.filters = Object.assign({ period: "30" }, prefs.filtros || {});
            this.state.hidden = prefs.ocultas || [];
            this.state.showFilters = FILTER_KEYS.some((k) => this.state.filters[k]);
            await this.load();
        });
        onMounted(() => {
            this.timer = setInterval(() => {
                if (!document.hidden) {
                    this.load();
                }
            }, REFRESH_MS);
        });
        onWillUnmount(() => {
            clearInterval(this.timer);
            clearTimeout(this.saveTimer);
            this.destroyCharts();
        });
        useEffect(
            () => this.renderCharts(),
            () => [this.state.data, this.state.hidden.length]
        );
    }

    // -- Datos y filtros ----------------------------------------------------------
    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("mirabilenet.dashboard", "get_dashboard_data", [
                this.state.filters,
            ]);
        } finally {
            this.state.loading = false;
        }
    }

    savePreferences() {
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => {
            this.orm.call("mirabilenet.dashboard", "save_preferences", [
                { filtros: this.state.filters, ocultas: this.state.hidden },
            ]);
        }, 800);
    }

    applyFilters(filters) {
        this.state.filters = filters;
        this.savePreferences();
        this.load();
    }

    setFilter(key, value) {
        const filters = Object.assign({}, this.state.filters);
        if (value === "" || value === null || value === undefined || value === false) {
            delete filters[key];
        } else {
            filters[key] = value;
        }
        // Una zona o un nodo de otra región no tienen sentido al cambiar de región.
        if (key === "region_id") {
            delete filters.zone_id;
            delete filters.node_id;
        }
        if (key === "zone_id") {
            delete filters.node_id;
        }
        this.applyFilters(filters);
    }

    setPeriod(period) {
        const filters = Object.assign({}, this.state.filters, { period });
        if (period === "rango") {
            const today = luxon.DateTime.local();
            filters.date_from = filters.date_from || today.minus({ days: 29 }).toISODate();
            filters.date_to = filters.date_to || today.toISODate();
        } else {
            delete filters.date_from;
            delete filters.date_to;
        }
        this.applyFilters(filters);
    }

    setDate(key, ev) {
        if (ev.target.value) {
            this.applyFilters(Object.assign({}, this.state.filters, { [key]: ev.target.value }));
        }
    }

    setRange(desde, hasta) {
        this.applyFilters(Object.assign({}, this.state.filters, {
            period: "rango",
            date_from: desde,
            date_to: hasta,
        }));
    }

    onSelect(key, ev) {
        const raw = ev.target.value;
        this.setFilter(key, ID_FILTERS.includes(key) && raw ? parseInt(raw) : raw);
    }

    removeChip(chip) {
        this.setFilter(chip.clave, false);
    }

    clearFilters() {
        const filters = { period: this.state.filters.period };
        if (filters.period === "rango") {
            filters.date_from = this.state.filters.date_from;
            filters.date_to = this.state.filters.date_to;
        }
        this.applyFilters(filters);
    }

    toggleFilters() {
        this.state.showFilters = !this.state.showFilters;
    }

    // Zonas, nodos y planes que corresponden a la región y zona elegidas.
    get zones() {
        const region = this.state.filters.region_id;
        return (this.state.options?.zonas || []).filter((z) => !region || z.region_id === region);
    }

    get nodes() {
        const { region_id: region, zone_id: zone } = this.state.filters;
        return (this.state.options?.nodos || []).filter(
            (n) => (!region || n.region_id === region) && (!zone || n.zone_id === zone)
        );
    }

    get plans() {
        const region = this.state.filters.region_id;
        return (this.state.options?.planes || []).filter(
            (p) => !region || !p.region_id || p.region_id === region
        );
    }

    get chips() {
        return this.data?.filtros?.chips || [];
    }

    // -- Personalizar -------------------------------------------------------------
    toggleCustomize() {
        this.state.customizing = !this.state.customizing;
    }

    toggleSection(section) {
        const hidden = new Set(this.state.hidden);
        if (hidden.has(section)) {
            hidden.delete(section);
        } else {
            hidden.add(section);
        }
        this.state.hidden = [...hidden];
        this.savePreferences();
    }

    resetLayout() {
        this.state.hidden = [];
        this.savePreferences();
    }

    get sections() {
        return (this.data?.secciones?.orden || []).filter((s) => !this.state.hidden.includes(s));
    }

    get allSections() {
        return this.data?.secciones?.orden || [];
    }

    // -- Abrir listas y pantallas ---------------------------------------------------
    async open(key, ev) {
        const action = await this.orm.call("mirabilenet.dashboard", "action_open", [
            key,
            this.state.filters,
        ]);
        this.actionService.doAction(action, { newWindow: Boolean(ev && (ev.ctrlKey || ev.metaKey)) });
    }

    async openAction(xmlid) {
        try {
            await this.actionService.doAction(xmlid);
        } catch {
            this.notification.add(_t("No tiene acceso a esa pantalla o no está instalada."), {
                type: "warning",
            });
        }
    }

    openPayment(id) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.payment",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // -- Formato -----------------------------------------------------------------
    money(value) {
        return value === null || value === undefined ? "—" : `${this.currency} ${MONEY.format(value)}`;
    }

    number(value) {
        return value === null || value === undefined ? "—" : INTEGER.format(value);
    }

    percent(value) {
        return value === null || value === undefined ? "—" : `${DECIMAL.format(value)} %`;
    }

    trend(value, unit = "%") {
        if (value === null || value === undefined) {
            return null;
        }
        const flat = value === 0;
        const up = value > 0;
        return {
            icon: flat ? "fa-minus" : up ? "fa-caret-up" : "fa-caret-down",
            css: flat ? "text-muted" : up ? "text-success" : "text-danger",
            text: `${up ? "+" : ""}${DECIMAL.format(value)} ${unit}`,
        };
    }

    get currency() {
        return this.state.data?.moneda || "Bs";
    }

    get data() {
        return this.state.data;
    }

    get periodLabel() {
        const f = this.data?.filtros;
        if (!f) {
            return "";
        }
        if (["hoy", "7", "30", "90"].includes(f.period)) {
            return PERIODS.find((p) => p.key === f.period)?.label || "";
        }
        return `${this.day(f.desde)} – ${this.day(f.hasta)}`;
    }

    get readAt() {
        const value = this.data?.generado;
        return value ? deserializeDateTime(value).toLocaleString({ hour: "numeric", minute: "2-digit" }) : "";
    }

    when(value) {
        const moment = deserializeDateTime(value);
        const today = luxon.DateTime.local().startOf("day");
        const time = moment.toLocaleString({ hour: "numeric", minute: "2-digit" });
        if (moment >= today) {
            return _t("Hoy, %s", time);
        }
        if (moment >= today.minus({ days: 1 })) {
            return _t("Ayer, %s", time);
        }
        return moment.toLocaleString({ day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    }

    day(value) {
        return deserializeDate(value).toLocaleString({ day: "numeric", month: "short" });
    }

    actionLabel(action) {
        const text = (action || "").replace(/[_.]/g, " ");
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    get totalServices() {
        return (this.data?.servicios_estado || []).reduce((sum, s) => sum + s.cantidad, 0);
    }

    get setupDone() {
        const setup = this.data?.puesta_en_marcha;
        return setup && setup.hechos === setup.total;
    }

    barWidth(value) {
        return value === null || value === undefined ? 0 : Math.min(value, 100);
    }

    occupancyClass(value) {
        return (value || 0) >= 90 ? "bg-danger" : (value || 0) >= 70 ? "bg-warning" : "bg-success";
    }

    agingWidth(amount) {
        const max = Math.max(1, ...(this.data?.negocio?.antiguedad || []).map((t) => t.monto));
        return Math.round((100 * (amount || 0)) / max);
    }

    // -- Gráficos ----------------------------------------------------------------
    destroyCharts() {
        for (const chart of Object.values(this.charts)) {
            chart.destroy();
        }
        this.charts = {};
    }

    chart(name, config) {
        const canvas = this.refs[name].el;
        if (!canvas || typeof Chart === "undefined") {
            return;
        }
        const text = cssColor("--body-color", "#495057");
        const grid = cssColor("--border-color", "#dee2e6");
        const onPick = config.onPick;
        delete config.onPick;
        config.options = Object.assign(
            {
                responsive: true,
                maintainAspectRatio: false,
                animation: this.firstDraw ? false : { duration: 400 },
                plugins: { legend: { labels: { color: text } } },
            },
            config.options || {}
        );
        if (config.options.scales) {
            for (const axis of Object.values(config.options.scales)) {
                axis.ticks = Object.assign({ color: text }, axis.ticks || {});
                axis.grid = Object.assign({ color: grid }, axis.grid || {});
            }
        }
        if (onPick) {
            config.options.onClick = (event, elements) => {
                if (elements.length) {
                    onPick(elements[0].index, event.native);
                }
            };
            config.options.onHover = (event, elements) => {
                event.native.target.style.cursor = elements.length ? "pointer" : "default";
            };
        }
        this.charts[name] = new Chart(canvas, config);
    }

    renderCharts() {
        const data = this.data;
        this.destroyCharts();
        if (!data) {
            return;
        }
        const money = (v) => `${this.currency} ${MONEY.format(v)}`;
        const tooltipMoney = {
            callbacks: { label: (ctx) => `${ctx.dataset.label || ctx.label}: ${money(ctx.parsed.y ?? ctx.parsed)}` },
        };
        const success = cssColor("--success", "#28a745");
        const danger = cssColor("--danger", "#dc3545");
        const primary = cssColor("--primary", "#714b67");
        const flow = data.ingresos_gastos;
        if (flow && flow.con_movimientos) {
            const datasets = [
                { label: _t("Ingresos"), data: flow.meses.map((m) => m.ingresos), backgroundColor: success, borderRadius: 4 },
            ];
            if (flow.con_gastos) {
                datasets.push({ label: _t("Gastos"), data: flow.meses.map((m) => m.gastos || 0), backgroundColor: danger, borderRadius: 4 });
            }
            this.chart("income", {
                type: "bar",
                data: { labels: flow.meses.map((m) => m.etiqueta), datasets },
                options: {
                    scales: { x: {}, y: { beginAtZero: true, ticks: { callback: (v) => INTEGER.format(v) } } },
                    plugins: { tooltip: tooltipMoney },
                },
                // Clic en un mes: todo el tablero pasa a ese mes.
                onPick: (i) => this.setRange(flow.meses[i].desde, flow.meses[i].hasta),
            });
        }
        const states = (data.servicios_estado || []).filter((s) => s.cantidad);
        if (states.length) {
            this.chart("states", {
                type: "doughnut",
                data: {
                    labels: states.map((s) => s.etiqueta),
                    datasets: [{
                        data: states.map((s) => s.cantidad),
                        backgroundColor: states.map((s) => cssColor(...(STATE_COLORS[s.clave] || ["--gray", "#6c757d"]))),
                        borderWidth: 0,
                    }],
                },
                options: { cutout: "65%", plugins: { legend: { display: false } } },
                // Clic en un estado: filtra todo el tablero. Ctrl+clic abre la lista.
                onPick: (i, event) =>
                    event && (event.ctrlKey || event.metaKey)
                        ? this.open("servicios_" + states[i].clave)
                        : this.setFilter("service_state", states[i].clave),
            });
        }
        const daily = data.cobranza_diaria;
        if (daily && daily.total) {
            this.chart("daily", {
                type: "line",
                data: {
                    labels: daily.dias.map((d) => this.day(d.fecha)),
                    datasets: [{
                        label: _t("Cobrado"),
                        data: daily.dias.map((d) => d.monto),
                        borderColor: primary,
                        backgroundColor: primary.startsWith("#") && primary.length === 7 ? primary + "33" : primary,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 2,
                    }],
                },
                options: {
                    scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true } },
                    plugins: { legend: { display: false }, tooltip: tooltipMoney },
                },
            });
        }
        const methods = data.cobranza_metodo || [];
        if (methods.length) {
            this.chart("methods", {
                type: "doughnut",
                data: {
                    labels: methods.map((m) => m.etiqueta),
                    datasets: [{
                        data: methods.map((m) => m.monto),
                        backgroundColor: methods.map((_m, i) => cssColor(...PALETTE[i % PALETTE.length])),
                        borderWidth: 0,
                    }],
                },
                options: {
                    cutout: "65%",
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${money(ctx.parsed)}` } },
                    },
                },
            });
        }
        const moves = data.negocio?.movimientos || [];
        if (moves.some((m) => m.altas || m.bajas)) {
            this.chart("movements", {
                type: "bar",
                data: {
                    labels: moves.map((m) => m.etiqueta),
                    datasets: [
                        { label: _t("Altas"), data: moves.map((m) => m.altas), backgroundColor: success, borderRadius: 4 },
                        { label: _t("Bajas"), data: moves.map((m) => -m.bajas), backgroundColor: danger, borderRadius: 4 },
                        {
                            type: "line",
                            label: _t("Altas netas"),
                            data: moves.map((m) => m.netas),
                            borderColor: primary,
                            backgroundColor: primary,
                            tension: 0.3,
                        },
                    ],
                },
                options: {
                    scales: { x: { stacked: true }, y: { ticks: { callback: (v) => INTEGER.format(Math.abs(v)) } } },
                    plugins: {
                        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${INTEGER.format(Math.abs(ctx.parsed.y))}` } },
                    },
                },
                onPick: (i) => this.setRange(moves[i].desde, moves[i].hasta),
            });
        }
        this.firstDraw = true;
    }
}

registry.category("actions").add("mirabilenet_dashboard.tablero", MirabilenetDashboard);
