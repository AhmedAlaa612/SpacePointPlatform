import React, { useState, useEffect } from "react";
import { X, Rocket, FileText, Image as ImageIcon, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { StudentMission, StudentMissionCreateInput, StudentMissionUpdateInput } from "@/types/cms";

interface StudentMissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: StudentMissionCreateInput | StudentMissionUpdateInput) => Promise<void>;
  missionToEdit?: StudentMission | null;
  isSaving: boolean;
}

export const StudentMissionModal: React.FC<StudentMissionModalProps> = ({
  isOpen,
  onClose,
  onSave,
  missionToEdit,
  isSaving,
}) => {
  const [studentName, setStudentName] = useState("");
  const [projectTitle, setProjectTitle] = useState("");
  const [category, setCategory] = useState("Autonomous Drone / Robotics");
  const [description, setDescription] = useState("");
  const [photoUrl, setPhotoUrl] = useState("");
  const [docxUrl, setDocxUrl] = useState("");
  const [metricsJsonStr, setMetricsJsonStr] = useState("{}");
  const [displayOrder, setDisplayOrder] = useState<number>(0);
  const [isActive, setIsActive] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (missionToEdit) {
      setStudentName(missionToEdit.student_name);
      setProjectTitle(missionToEdit.project_title);
      setCategory(missionToEdit.category);
      setDescription(missionToEdit.description);
      setPhotoUrl(missionToEdit.photo_url || "");
      setDocxUrl(missionToEdit.docx_url || "");
      setMetricsJsonStr(JSON.stringify(missionToEdit.metrics_json || {}, null, 2));
      setDisplayOrder(missionToEdit.display_order);
      setIsActive(missionToEdit.is_active);
    } else {
      setStudentName("");
      setProjectTitle("");
      setCategory("Robotics & Autonomy");
      setDescription("");
      setPhotoUrl("");
      setDocxUrl("");
      setMetricsJsonStr('{\n  "altitude": "32 km",\n  "status": "Flight Verified"\n}');
      setDisplayOrder(0);
      setIsActive(true);
    }
    setErrorMsg(null);
  }, [missionToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!studentName.trim()) {
      setErrorMsg("Please enter student name.");
      return;
    }
    if (!projectTitle.trim()) {
      setErrorMsg("Please enter project title.");
      return;
    }
    if (!description.trim()) {
      setErrorMsg("Please enter project description.");
      return;
    }

    let parsedMetrics = {};
    try {
      if (metricsJsonStr.trim()) {
        parsedMetrics = JSON.parse(metricsJsonStr);
      }
    } catch {
      setErrorMsg("Invalid JSON format in Metrics.");
      return;
    }

    try {
      await onSave({
        student_name: studentName.trim(),
        project_title: projectTitle.trim(),
        category: category.trim(),
        description: description.trim(),
        photo_url: photoUrl.trim() || null,
        docx_url: docxUrl.trim() || null,
        metrics_json: parsedMetrics,
        display_order: displayOrder,
        is_active: isActive,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to save student mission.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-xl max-h-[92vh] flex flex-col bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Rocket className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold font-display text-foreground">
                {missionToEdit ? "Edit Student Mission" : "Add Student Project"}
              </h2>
              <p className="text-xs text-muted-foreground">
                Showcase student research, high-altitude balloons, and robotics projects.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {errorMsg && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-destructive text-xs">
              {errorMsg}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Student / Lead Name <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Fatima Al Hosani"
                value={studentName}
                onChange={(e) => setStudentName(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Category
              </label>
              <input
                type="text"
                placeholder="e.g. Satellite Biology, Balloon Payloads"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Project Title <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              placeholder="e.g. Microgravity Seed Germination Experiment"
              value={projectTitle}
              onChange={(e) => setProjectTitle(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Project Description <span className="text-destructive">*</span>
            </label>
            <textarea
              rows={3}
              placeholder="Detailed description of the student's research, experiment design, and telemetry findings..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full p-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Project Photo URL or Path
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="/assets/students/project1.png"
                  value={photoUrl}
                  onChange={(e) => setPhotoUrl(e.target.value)}
                  className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <ImageIcon className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Document (.docx) URL
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="/assets/students/paper.docx"
                  value={docxUrl}
                  onChange={(e) => setDocxUrl(e.target.value)}
                  className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <FileText className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Project Metrics (JSON)
            </label>
            <textarea
              rows={3}
              value={metricsJsonStr}
              onChange={(e) => setMetricsJsonStr(e.target.value)}
              className="w-full p-3 rounded-xl border border-border bg-background font-mono text-[11px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4 pt-1">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Display Order
              </label>
              <input
                type="number"
                min={0}
                value={displayOrder}
                onChange={(e) => setDisplayOrder(parseInt(e.target.value, 10) || 0)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            <div className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                id="is_active_mission"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="is_active_mission" className="text-xs font-medium text-foreground cursor-pointer">
                Showcase on Website
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={isSaving} className="gap-1.5">
              <Save className="w-3.5 h-3.5" />
              Save Project
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
