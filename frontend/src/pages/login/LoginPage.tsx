import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, Button, Typography, App } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";

const { Title, Text } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const { message } = App.useApp();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      navigate("/dashboard", { replace: true });
    } catch {
      message.error("用户名或密码错误");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--qf-bg-base)",
        position: "relative",
        overflow: "hidden",
        padding: 24,
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
            padding: "40px 36px",
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
              智能质量管理平台 · 精密熔炉
            </Text>
          </div>

          <Form onFinish={onFinish} size="large" layout="vertical">
            <Form.Item
              name="username"
              rules={[{ required: true, message: "请输入用户名" }]}
              style={{ marginBottom: 20 }}
            >
              <Input
                prefix={<UserOutlined style={{ color: "var(--qf-cyan)", marginRight: 8 }} />}
                placeholder="用户名"
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
              rules={[{ required: true, message: "请输入密码" }]}
              style={{ marginBottom: 28 }}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: "var(--qf-cyan)", marginRight: 8 }} />}
                placeholder="密码"
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
                登录
              </Button>
            </Form.Item>
          </Form>

          <Text
            style={{
              display: "block",
              textAlign: "center",
              fontSize: 12,
              color: "var(--qf-text-tertiary)",
              marginTop: 24,
              fontFamily: "var(--qf-font-mono)",
            }}
          >
            默认账号 admin / Admin@2026
          </Text>
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
          © OpenQMS · 中国制造质量操作系统
        </Text>
      </div>
    </div>
  );
}
