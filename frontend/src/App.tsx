import { Routes, Route, Navigate } from "react-router-dom";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<div style={{ padding: 48, textAlign: "center" }}>OpenQMS MVP — Coming Soon</div>} />
    </Routes>
  );
}

export default App;
