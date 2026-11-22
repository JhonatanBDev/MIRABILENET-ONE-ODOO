import { MirabilenetDynamic } from "./mn_dynamic";
import { registry } from "@web/core/registry";

/** En el editor, sin datos publicados, se ven datos de muestra y los enlaces no navegan. */
const MirabilenetDynamicEdit = (I) =>
    class extends I {
        setup() {
            super.setup();
            this.withSample = true;
        }
        callToAction() {}
    };

registry.category("public.interactions.edit").add("mirabilenet_web.dynamic", {
    Interaction: MirabilenetDynamic,
    mixin: MirabilenetDynamicEdit,
});
