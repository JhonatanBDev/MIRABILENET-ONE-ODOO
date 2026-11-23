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
    { key: "7", label: _t("Últimos 7 días") },
    { key: "30", label: _t("Últimos 30 días") },
    { key: "90", label: _t("Últimos 90 días") },
];
const SHORTCUTS = [
    { label: _t("Clientes"), icon: "fa-users", xmlid: "mirabilenet_isp.action_mirabilenet_customer" },
    { label: _t("Contratos"), icon: "fa-file-text-o", xmlid: "contract.action_customer_contract" },
    { label: _t("Pagos"), icon: "fa-money", xmlid: "account.action_account_payments" },
    { label: _t("Routers"), icon: "fa-server", xmlid: "mirabilenet_isp.action_mirabilenet_router" },
    { label: _t("Planes"), icon: "fa-tags", xmlid: "mirabilenet_isp.action_mirabilenet_plan" },
    { label: _t("Mapa de fibra"), icon: "fa-map-o", xmlid: "mirabilenet_fibra.action_mirabilenet_fiber_map" },
    { label: _t("Auditoría"), icon: "fa-history", xmlid: "mirabilenet_base.action_mirabilenet_audit_log" },
];
// Color de cada estado del servicio (variables de Bootstrap: siguen el modo oscuro).
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
const MONEY = new Intl.NumberFormat("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const INTEGER = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 0 });

function cssColor(variable, fallback) {
    // Odoo define las variables de Bootstrap en el body (y las cambia en modo oscuro).
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
        this.refs = {
            income: useRef("incomeChart"),
            states: useRef("statesChart"),
            daily: useRef("dailyChart"),
            methods: useRef("methodsChart"),
        };
        this.charts = {};
        this.state = useState({ data: null, period: "30", regionId: false, loading: false });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
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
            this.destroyCharts();
        });
        useEffect(
            () => this.renderCharts(),
            () => [this.state.data]
        );
    }

    // -- Datos -------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("mirabilenet.dashboard", "get_dashboard_data", [
                this.state.period,
                this.state.regionId,
            ]);
        } finally {
            this.state.loading = false;
        }
    }

    setPeriod(period) {
        this.state.period = period;
        this.load();
    }

    onRegionChange(ev) {
        this.state.regionId = ev.target.value ? parseInt(ev.target.value) : false;
        this.load();
    }

    async open(key) {
        const action = await this.orm.call("mirabilenet.dashboard", "action_open", [
            key,
            this.state.period,
            this.state.regionId,
        ]);
        this.actionService.doAction(action);
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
        return value === null || value === undefined ? "—" : `${MONEY.format(value)} %`;
    }

    get currency() {
        return this.state.data?.moneda || "Bs";
    }

    get data() {
        return this.state.data;
    }

    get periodLabel() {
        return PERIODS.find((p) => p.key === this.state.period)?.label || "";
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

    get occupancyWidth() {
        const value = this.data?.capacidad?.ocupacion;
        return value === null || value === undefined ? 0 : Math.min(value, 100);
    }

    get occupancyClass() {
        const value = this.data?.capacidad?.ocupacion || 0;
        return value >= 90 ? "bg-danger" : value >= 70 ? "bg-warning" : "bg-success";
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
        this.charts[name] = new Chart(canvas, config);
    }

    renderCharts() {
        const data = this.data;
        this.destroyCharts();
        if (!data) {
            return;
        }
        const money = (v) => `${this.currency} ${MONEY.format(v)}`;
        const tooltipMoney = { callbacks: { label: (ctx) => `${ctx.dataset.label || ctx.label}: ${money(ctx.parsed.y ?? ctx.parsed)}` } };
        const flow = data.ingresos_gastos;
        if (flow && flow.con_movimientos) {
            const datasets = [
                {
                    label: _t("Ingresos"),
                    data: flow.meses.map((m) => m.ingresos),
                    backgroundColor: cssColor("--success", "#28a745"),
                    borderRadius: 4,
                },
            ];
            if (flow.con_gastos) {
                datasets.push({
                    label: _t("Gastos"),
                    data: flow.meses.map((m) => m.gastos || 0),
                    backgroundColor: cssColor("--danger", "#dc3545"),
                    borderRadius: 4,
                });
            }
            this.chart("income", {
                type: "bar",
                data: { labels: flow.meses.map((m) => m.etiqueta), datasets },
                options: {
                    scales: { x: {}, y: { beginAtZero: true, ticks: { callback: (v) => INTEGER.format(v) } } },
                    plugins: { tooltip: tooltipMoney },
                },
            });
        }
        const states = (data.servicios_estado || []).filter((s) => s.cantidad);
        if (states.length) {
            this.chart("states", {
                type: "doughnut",
                data: {
                    labels: states.map((s) => s.etiqueta),
                    datasets: [
                        {
                            data: states.map((s) => s.cantidad),
                            backgroundColor: states.map((s) => cssColor(...(STATE_COLORS[s.clave] || ["--gray", "#6c757d"]))),
                            borderWidth: 0,
                        },
                    ],
                },
                options: { cutout: "65%", plugins: { legend: { display: false } } },
            });
        }
        const daily = data.cobranza_diaria;
        if (daily && daily.total) {
            const primary = cssColor("--primary", "#714b67");
            this.chart("daily", {
                type: "line",
                data: {
                    labels: daily.dias.map((d) => this.day(d.fecha)),
                    datasets: [
                        {
                            label: _t("Cobrado"),
                            data: daily.dias.map((d) => d.monto),
                            borderColor: primary,
                            backgroundColor: primary.startsWith("#") && primary.length === 7 ? primary + "33" : primary,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 2,
                        },
                    ],
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
                    datasets: [
                        {
                            data: methods.map((m) => m.monto),
                            backgroundColor: methods.map((_m, i) => cssColor(...PALETTE[i % PALETTE.length])),
                            borderWidth: 0,
                        },
                    ],
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
        this.firstDraw = true;
    }
}

registry.category("actions").add("mirabilenet_dashboard.tablero", MirabilenetDashboard);
