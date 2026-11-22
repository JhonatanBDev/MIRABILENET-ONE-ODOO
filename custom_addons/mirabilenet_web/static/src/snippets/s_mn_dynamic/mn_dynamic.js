import { DynamicSnippet, DynamicSnippetCached } from "@website/snippets/s_dynamic_snippet/dynamic_snippet";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/**
 * Bloques dinámicos de MIRABILENET (servicios, planes, cobertura...). Es el bloque dinámico de
 * Odoo; lo único propio es que el bloque dice qué lista muestra («data-mn-filter») y aquí se
 * busca el filtro que le corresponde, porque su número cambia de una base a otra.
 */
export class MirabilenetDynamic extends DynamicSnippet {
    static selector = ".s_mn_dynamic";

    async willStart() {
        const dataset = this.el.dataset;
        if (!dataset.filterId && dataset.mnFilter) {
            const filterId = await this.waitFor(
                rpc("/mirabilenet/web/filtro", { clave: dataset.mnFilter })
            );
            if (filterId) {
                dataset.filterId = filterId;
            }
        }
        await super.willStart();
    }
}

registry.category("public.interactions").add("mirabilenet_web.dynamic", MirabilenetDynamic);

registry.category("public.interactions.preview").add("mirabilenet_web.dynamic", {
    Interaction: MirabilenetDynamic,
    mixin: DynamicSnippetCached,
});
