import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";

export default function TenantSuspended() {
  const navigate = useNavigate();
  return (
    <Result
      status="warning"
      title="租户已暂停"
      subTitle="您的租户账户已被暂停，请联系管理员。"
      extra={<Button type="primary" onClick={() => navigate("/login")}>返回登录</Button>}
    />
  );
}