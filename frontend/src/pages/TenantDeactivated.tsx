import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";

export default function TenantDeactivated() {
  const navigate = useNavigate();
  return (
    <Result
      status="error"
      title="租户已停用"
      subTitle="您的租户账户已被停用，数据已保留但不可访问。"
      extra={<Button type="primary" onClick={() => navigate("/login")}>返回登录</Button>}
    />
  );
}