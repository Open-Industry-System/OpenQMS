import { useState, useEffect } from "react"
import { Modal, Select, Table, Button, App } from "antd"
import type { TableRowSelection } from "antd/es/table/interface"
import { listFMEAs } from "../../api/fmea"
import { importFromFMEA } from "../../api/controlPlan"
import type { FMEADocument, GraphNode } from "../../types"

interface Props {
  cpId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

interface StepRow {
  key: string
  process_number: string
  name: string
}

export default function ImportFromFMEAModal({ cpId, open, onClose, onSuccess }: Props) {
  const { message } = App.useApp();
  const [fmeas, setFmeas] = useState<FMEADocument[]>([])
  const [selectedFmeaId, setSelectedFmeaId] = useState<string | null>(null)
  const [steps, setSteps] = useState<StepRow[]>([])
  const [selectedStepKeys, setSelectedStepKeys] = useState<React.Key[]>([])
  const [loadingFmeas, setLoadingFmeas] = useState(false)
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    if (!open) return

    setSelectedFmeaId(null)
    setSteps([])
    setSelectedStepKeys([])
    setImporting(false)

    setLoadingFmeas(true)
    listFMEAs({ status: "approved", page_size: 100 })
      .then((resp) => {
        const pfmeas = resp.items.filter((f) => f.fmea_type === "PFMEA")
        setFmeas(pfmeas)
      })
      .catch(() => {
        message.error("加载 PFMEA 列表失败")
      })
      .finally(() => {
        setLoadingFmeas(false)
      })
  }, [open])

  const handleSelectFMEA = (fmeaId: string) => {
    setSelectedFmeaId(fmeaId)
    const fmea = fmeas.find((f) => f.fmea_id === fmeaId)
    if (!fmea) {
      setSteps([])
      setSelectedStepKeys([])
      return
    }

    const processSteps: StepRow[] = (fmea.graph_data?.nodes || [])
      .filter((n: GraphNode) => n.type === "ProcessStep")
      .map((n: GraphNode) => ({
        key: n.id,
        process_number: n.process_number || "",
        name: n.name,
      }))

    setSteps(processSteps)
    setSelectedStepKeys(processSteps.map((s) => s.key))
  }

  const handleOk = async () => {
    if (!selectedFmeaId) {
      message.warning("请先选择 PFMEA")
      return
    }

    const selectedStepNos = steps
      .filter((s) => selectedStepKeys.includes(s.key))
      .map((s) => s.process_number)

    setImporting(true)
    try {
      await importFromFMEA(cpId, selectedFmeaId, selectedStepNos.length > 0 ? selectedStepNos : undefined)
      message.success("导入成功")
      onSuccess()
      onClose()
    } catch (e: any) {
      message.error(e.response?.data?.detail || "导入失败")
    } finally {
      setImporting(false)
    }
  }

  const rowSelection: TableRowSelection<StepRow> = {
    selectedRowKeys: selectedStepKeys as string[],
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedStepKeys(newSelectedRowKeys)
    },
  }

  const columns = [
    {
      title: "工序号",
      dataIndex: "process_number",
      key: "process_number",
    },
    {
      title: "工序名称",
      dataIndex: "name",
      key: "name",
    },
  ]

  return (
    <Modal
      title="从 PFMEA 导入"
      open={open}
      onCancel={onClose}
      width={700}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="ok"
          type="primary"
          loading={importing}
          onClick={handleOk}
        >
          确定
        </Button>,
      ]}
    >
      <div style={{ marginBottom: 16 }}>
        <Select
          style={{ width: "100%" }}
          placeholder="选择已批准的 PFMEA"
          loading={loadingFmeas}
          value={selectedFmeaId}
          onChange={handleSelectFMEA}
          options={fmeas.map((f) => ({
            value: f.fmea_id,
            label: `${f.document_no} - ${f.title}`,
          }))}
        />
      </div>

      {steps.length > 0 && (
        <Table
          rowSelection={rowSelection}
          columns={columns}
          dataSource={steps}
          pagination={false}
          size="small"
          rowKey="key"
        />
      )}
    </Modal>
  )
}
