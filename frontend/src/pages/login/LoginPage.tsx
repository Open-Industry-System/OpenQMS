import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, Button, Card, Typography, App, Space } from "antd";
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
        justifyContent: "center",
        alignItems: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Card style={{ width: 400, boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div style={{ textAlign: "center" }}>
            <Title level={3} style={{ margin: 0 }}>
              OpenQMS
            </Title>
            <Text type="secondary">智能质量管理平台</Text>
          </div>
          <Form onFinish={onFinish} size="large">
            <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary" style={{ display: "block", textAlign: "center", fontSize: 12 }}>
            默认账号: admin / Admin@2026
          </Text>
        </Space>
      </Card>
    </div>
  );
}
