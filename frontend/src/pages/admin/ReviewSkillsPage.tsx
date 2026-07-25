import { useEffect, useState } from "react";
import { Button, Card, Drawer, Form, Input, message, Table } from "antd";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import type { ReviewSkill } from "../../types";

export default function ReviewSkillsPage() {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<ReviewSkill[]>([]);
  const [editing, setEditing] = useState<ReviewSkill | null>(null);
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const r = await client.get("/admin/review-skills");
    setSkills(r.data);
  };
  useEffect(() => { load(); }, []);

  const openEdit = (s: ReviewSkill) => { setEditing(s); setContent(s.content); };
  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await client.put(`/admin/review-skills/${editing.name}`, { content });
      message.success(t("admin:reviewSkills.save"));
      setEditing(null);
      await load();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title={t("admin:reviewSkills.title")}>
      <Table dataSource={skills} rowKey="skill_id" columns={[
        { title: "name", dataIndex: "name" },
        { title: "version", dataIndex: "version" },
        { title: "tenant", dataIndex: "tenant_schema" },
        { title: "action", render: (_, r) => <Button onClick={() => openEdit(r)}>{t("admin:reviewSkills.edit")}</Button> },
      ]} />
      <Drawer open={editing !== null} onClose={() => setEditing(null)} title={t("admin:reviewSkills.edit")} width={600}
        extra={<Button type="primary" loading={saving} onClick={save}>{t("admin:reviewSkills.save")}</Button>}>
        <Form layout="vertical">
          <Form.Item label={t("admin:reviewSkills.content")}>
            <Input.TextArea value={content} onChange={(e) => setContent(e.target.value)} rows={20} />
          </Form.Item>
        </Form>
      </Drawer>
    </Card>
  );
}
