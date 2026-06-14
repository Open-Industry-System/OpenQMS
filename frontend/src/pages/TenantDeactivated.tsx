import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { PageShell } from "../components/design";

export default function TenantDeactivated() {
  const navigate = useNavigate();
  return (
    <PageShell
      title="租户已停用"
      actions={
        <Button type="primary" onClick={() => navigate("/login")}>
          返回登录
        </Button>
      }
    >
      <Result
        status="error"
        subTitle="您的租户账户已被停用，数据已保留但不可访问。"
      />
    </PageShell>
  );
}
