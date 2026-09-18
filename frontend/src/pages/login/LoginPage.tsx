import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Form, Input, Button, Typography, App, Alert, Space } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import LanguageSwitcher from "../../components/LanguageSwitcher";
import { getPublicDemoConfig } from "../../config/publicDemo";

const { Title, Text } = Typography;

type DemoRole = "viewer" | "admin" | "engineer" | "manager" | "groupadmin";

export default function LoginPage() {
  const { t } = useTranslation("login");
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ username: string; password: string }>();
  const [searchParams] = useSearchParams();
  const configuredDemo = getPublicDemoConfig();
  const demoAccounts = configuredDemo
    ? [
      { username: configuredDemo.username, password: configuredDemo.password, role: "viewer" as const },
      ...(configuredDemo.additionalAccounts ?? []).map((account) => ({
        ...account,
        role: account.username as Exclude<DemoRole, "viewer">,
      })),
    ]
    : [];
  const isMultiRoleDemo = demoAccounts.length === 5;
  const showDemo = Boolean(configuredDemo && (isMultiRoleDemo || searchParams.get("demo") === "viewer"));

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
        maxHeight: "100vh",
        display: "flex",
        alignItems: "safe center",
        justifyContent: "center",
        background: "var(--qf-bg-base)",
        position: "relative",
        overflowX: "hidden",
        overflowY: "auto",
        padding: "24px 16px",
      }}
    >
      {/* 背景网格 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(0, 229, 255, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 229, 255, 0.04) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
          maskImage: "radial-gradient(circle at 50% 40%, black 0%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 40%, black 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* 浮动光晕 */}
      <div
        style={{
          position: "absolute",
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(0, 229, 255, 0.12) 0%, transparent 65%)",
          top: "-120px",
          right: "-120px",
          filter: "blur(40px)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(0, 214, 143, 0.08) 0%, transparent 65%)",
          bottom: "-100px",
          left: "-100px",
          filter: "blur(50px)",
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          width: 420,
          maxWidth: "100%",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div
          style={{
            background: "var(--qf-bg-panel)",
            border: "1px solid var(--qf-border)",
            borderRadius: "var(--qf-radius-lg)",
            boxShadow: "var(--qf-shadow-glow), var(--qf-shadow-md)",
            padding: "32px clamp(16px, 8vw, 36px)",
          }}
        >
          <div style={{ textAlign: "center", marginBottom: 36 }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 12,
                background: "linear-gradient(135deg, var(--qf-cyan), #00b8d4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px",
                boxShadow: "0 0 24px rgba(0, 229, 255, 0.35)",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--qf-font-mono)",
                  fontSize: 28,
                  fontWeight: 700,
                  color: "#0b0d12",
                }}
              >
                Q
              </span>
            </div>
            <Title
              level={3}
              style={{
                margin: 0,
                fontFamily: "var(--qf-font-display)",
                fontSize: 28,
                letterSpacing: "0.04em",
                color: "var(--qf-text-primary)",
              }}
            >
              OpenQMS
            </Title>
            <Text style={{ color: "var(--qf-text-secondary)", fontSize: 13 }}>
              {t("subtitle")}
            </Text>
          </div>

          {showDemo && (
            <Alert
              type="info"
              showIcon
              message={t(isMultiRoleDemo ? "demo.multiRoleTitle" : "demo.title")}
              description={(
                <Space direction="vertical" size={isMultiRoleDemo ? 6 : 8} style={{ width: "100%" }}>
                  <Text>{t(isMultiRoleDemo ? "demo.sharedWarning" : "demo.description")}</Text>
                  {demoAccounts.map((account) => {
                    const role = t(`demo.roles.${account.role}`);
                    return (
                      <Space direction="vertical" size={2} key={account.role} style={{ width: "100%" }}>
                        <Text strong>{role}</Text>
                        <Text>
                          {t("demo.username")}: <Text code style={{ wordBreak: "break-all" }}>{account.username}</Text>
                        </Text>
                        <Text>
                          {t("demo.password")}: <Text code style={{ wordBreak: "break-all" }}>{account.password}</Text>
                        </Text>
                        <Button
                          type="link"
                          onClick={() => form.setFieldsValue({
                            username: account.username,
                            password: account.password,
                          })}
                          style={{ padding: 0, alignSelf: "flex-start" }}
                        >
                          {t("demo.fill", { role })}
                        </Button>
                      </Space>
                    );
                  })}
                </Space>
              )}
              style={{ marginBottom: 24 }}
            />
          )}

          <Form form={form} onFinish={onFinish} size="large" layout="vertical">
            <Form.Item
              name="username"
              rules={[{ required: true, message: t("usernameRequired") }]}
              style={{ marginBottom: 20 }}
            >
              <Input
                prefix={<UserOutlined style={{ color: "var(--qf-cyan)", marginRight: 8 }} />}
                placeholder={t("username")}
                style={{
                  background: "var(--qf-bg-input)",
                  borderColor: "var(--qf-border)",
                  color: "var(--qf-text-primary)",
                  fontFamily: "var(--qf-font-body)",
                }}
              />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[{ required: true, message: t("passwordRequired") }]}
              style={{ marginBottom: 28 }}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: "var(--qf-cyan)", marginRight: 8 }} />}
                placeholder={t("password")}
                style={{
                  background: "var(--qf-bg-input)",
                  borderColor: "var(--qf-border)",
                  color: "var(--qf-text-primary)",
                  fontFamily: "var(--qf-font-body)",
                }}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                size="large"
                style={{
                  height: 48,
                  fontSize: 16,
                  fontWeight: 600,
                  borderRadius: "var(--qf-radius-md)",
                }}
                className="qf-btn-primary"
              >
                {t("login")}
              </Button>
            </Form.Item>
          </Form>
        </div>

        <div style={{ textAlign: "center", marginTop: 16 }}>
          <LanguageSwitcher />
        </div>

        <Text
          style={{
            display: "block",
            textAlign: "center",
            fontSize: 11,
            color: "var(--qf-text-tertiary)",
            marginTop: 16,
          }}
        >
          {t("footer")}
        </Text>
      </div>
    </div>
  );
}
