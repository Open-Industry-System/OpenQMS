import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { PageShell } from "../components/design";

export default function TenantSuspended() {
  const navigate = useNavigate();
  return (
    <PageShell
      title="租户已暂停"
      actions={
        <Button type="primary" onClick={() => navigate("/login")}>
          返回登录
        </Button>
      }
    >
      <Result
        status="warning"
        subTitle="您的租户账户已被暂停，请联系管理员。"
      />
    </PageShell>
  );
}
