import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, Button, Card, Typography, App, Space, Segmented } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import { useAuthStore } from "../../store/authStore";

const { Title, Text } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { t } = useTranslation("login");

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success(t("loginSuccess"));
      navigate("/dashboard", { replace: true });
    } catch {
      message.error(t("loginError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Card style={{ width: 400, boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div style={{ textAlign: "center" }}>
            <Title level={3} style={{ margin: 0 }}>
              {t("title")}
            </Title>
            <Text type="secondary">{t("subtitle")}</Text>
          </div>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <Segmented
              value={i18n.language}
              onChange={(value) => i18n.changeLanguage(value as string)}
              options={[
                { label: "中文", value: "zh-CN" },
                { label: "English", value: "en-US" },
              ]}
            />
          </div>
          <Form onFinish={onFinish} size="large">
            <Form.Item name="username" rules={[{ required: true, message: t("usernameRequired") }]}>
              <Input prefix={<UserOutlined />} placeholder={t("usernamePlaceholder")} />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: t("passwordRequired") }]}>
              <Input.Password prefix={<LockOutlined />} placeholder={t("passwordPlaceholder")} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                {t("login")}
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary" style={{ display: "block", textAlign: "center", fontSize: 12 }}>
            {t("defaultAccount")}
          </Text>
        </Space>
      </Card>
    </div>
  );
}
