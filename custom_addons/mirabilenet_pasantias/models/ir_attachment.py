import os

from odoo import api, models, _
from odoo.exceptions import ValidationError

from .project_task import is_intern

#: Lista blanca. Nunca incluye .html, .htm ni .svg: ejecutarían JavaScript en el mismo origen.
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf", ".xls", ".xlsx", ".ods", ".csv",
    ".ppt", ".pptx", ".odp", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".mp4", ".mov",
    ".webm", ".zip", ".rar", ".7z", ".tar", ".gz", ".stl", ".step", ".stp", ".3mf", ".obj",
    ".igs", ".iges", ".f3d", ".f3z", ".sldprt", ".sldasm", ".ipt", ".iam", ".scad", ".dwg",
    ".dxf", ".kicad_pcb", ".kicad_sch", ".sch", ".brd", ".gbr", ".ino", ".hex", ".bin",
} - {".html", ".htm", ".svg"}
MAX_BYTES = 90 * 1024 * 1024


def check_file(name, size):
    extension = os.path.splitext((name or "").strip().lower())[1]
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(_("No se admite el archivo «%s» en una pasantía.", name or ""))
    if size > MAX_BYTES:
        raise ValidationError(_("«%s» pesa más de 90 MB.", name))


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        for attachment in attachments.sudo().filtered(
                lambda a: a.res_model == "project.task" and not a.res_field):
            task = self.env["project.task"].sudo().browse(attachment.res_id)
            if task.mirabilenet_internship:
                check_file(attachment.name, attachment.file_size)
                if is_intern(self.env):
                    task.with_env(self.env)._mirabilenet_owned()
        return attachments

    def unlink(self):
        if is_intern(self.env):
            tasks = self.env["project.task"].sudo().browse(self.sudo().filtered(
                lambda a: a.res_model == "project.task").mapped("res_id"))
            tasks.filtered("mirabilenet_internship").with_env(self.env)._mirabilenet_owned()
        return super().unlink()
