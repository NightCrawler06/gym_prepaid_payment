import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  FlatList,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import QRCode from "react-native-qrcode-svg";

import {
  addCredits,
  createMember,
  getDashboardStats,
  getLogs,
  getMembers,
  initializeDatabase,
  processScanToken,
} from "./src/database";

const tabs = [
  { key: "register", label: "Register" },
  { key: "members", label: "Members" },
  { key: "scanner", label: "Scanner" },
  { key: "logs", label: "Logs" },
];

const initialForm = {
  fullName: "",
  phone: "",
  email: "",
  credits: "5",
};

export default function App() {
  const [activeTab, setActiveTab] = useState("register");
  const [stats, setStats] = useState({
    totalMembers: 0,
    totalCredits: 0,
    todayPaidEntries: 0,
    lowCreditMembers: 0,
  });
  const [members, setMembers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedMemberId, setSelectedMemberId] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [latestMember, setLatestMember] = useState(null);
  const [topUpValue, setTopUpValue] = useState("5");
  const [scanMessage, setScanMessage] = useState("Waiting for scan.");
  const [scanTone, setScanTone] = useState("neutral");
  const [scannerEnabled, setScannerEnabled] = useState(true);
  const [permission, requestPermission] = useCameraPermissions();

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId) ?? null,
    [members, selectedMemberId]
  );

  async function refreshData() {
    const [statsResult, membersResult, logsResult] = await Promise.all([
      getDashboardStats(),
      getMembers(),
      getLogs(),
    ]);
    setStats(statsResult);
    setMembers(membersResult);
    setLogs(logsResult);
  }

  useEffect(() => {
    async function bootstrap() {
      await initializeDatabase();
      await refreshData();
    }
    bootstrap();
  }, []);

  useEffect(() => {
    const intervalId = setInterval(() => {
      refreshData().catch(() => null);
    }, 5000);

    return () => clearInterval(intervalId);
  }, []);

  async function handleRegister() {
    if (!form.fullName.trim()) {
      Alert.alert("Missing name", "Please enter the member's full name.");
      return;
    }

    const newMember = await createMember({
      fullName: form.fullName.trim(),
      phone: form.phone.trim(),
      email: form.email.trim(),
      initialCredits: Number(form.credits || 0),
    });

    setLatestMember(newMember);
    setForm(initialForm);
    await refreshData();
    Alert.alert("Member added", "Member registration and QR creation completed.");
  }

  async function handleTopUp() {
    if (!selectedMember) {
      Alert.alert("No member selected", "Please choose a member first.");
      return;
    }

    const amount = Number(topUpValue || 0);
    if (!amount || amount < 1) {
      Alert.alert("Invalid credits", "Enter a valid top-up amount.");
      return;
    }

    await addCredits(selectedMember.id, amount);
    await refreshData();
    Alert.alert("Credits updated", `${amount} credit(s) added successfully.`);
  }

  async function handleScan({ data }) {
    if (!scannerEnabled || !data) {
      return;
    }

    setScannerEnabled(false);

    try {
      const result = await processScanToken(data);
      if (result.status === "approved") {
        setScanTone("success");
        setScanMessage(
          `Payment accepted\n${result.member.full_name}\nRemaining credits: ${result.member.credits}`
        );
      } else if (result.status === "already_scanned") {
        setScanTone("warning");
        setScanMessage(
          `Already scanned today\n${result.member.full_name}\nRemaining credits: ${result.member.credits}`
        );
      } else {
        setScanTone("danger");
        setScanMessage(result.message);
      }
      await refreshData();
    } catch (error) {
      setScanTone("danger");
      setScanMessage("Scan failed. Please try again.");
    } finally {
      setTimeout(() => setScannerEnabled(true), 2500);
    }
  }

  const scanCardStyle = [
    styles.scanCard,
    scanTone === "success" && styles.scanSuccess,
    scanTone === "warning" && styles.scanWarning,
    scanTone === "danger" && styles.scanDanger,
  ];

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Gym QR Credit Mobile</Text>
          <Text style={styles.subtitle}>
            Phone app for member registration, credits, and QR scanning.
          </Text>
        </View>

        <View style={styles.statsRow}>
          <StatCard label="Members" value={stats.totalMembers} />
          <StatCard label="Credits" value={stats.totalCredits} />
          <StatCard label="Paid Today" value={stats.todayPaidEntries} />
          <StatCard label="Low Credit" value={stats.lowCreditMembers} />
        </View>

        <View style={styles.tabsRow}>
          {tabs.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tabButton, activeTab === tab.key && styles.tabButtonActive]}
              onPress={() => setActiveTab(tab.key)}
            >
              <Text
                style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}
              >
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          {activeTab === "register" && (
            <View style={styles.panel}>
              <Text style={styles.panelTitle}>Register Member</Text>
              <InputField
                label="Full Name"
                value={form.fullName}
                onChangeText={(text) => setForm((current) => ({ ...current, fullName: text }))}
                placeholder="Juan Dela Cruz"
              />
              <InputField
                label="Phone"
                value={form.phone}
                onChangeText={(text) => setForm((current) => ({ ...current, phone: text }))}
                placeholder="09XXXXXXXXX"
              />
              <InputField
                label="Email"
                value={form.email}
                onChangeText={(text) => setForm((current) => ({ ...current, email: text }))}
                placeholder="member@email.com"
              />
              <InputField
                label="Initial Credits"
                value={form.credits}
                onChangeText={(text) => setForm((current) => ({ ...current, credits: text }))}
                keyboardType="numeric"
                placeholder="5"
              />
              <PrimaryButton label="Register Member" onPress={handleRegister} />

              {latestMember ? (
                <View style={styles.qrBox}>
                  <Text style={styles.qrLabel}>Generated QR</Text>
                  <QRCode value={latestMember.qr_token} size={180} />
                  <Text style={styles.qrMeta}>{latestMember.full_name}</Text>
                  <Text style={styles.qrMeta}>Token: {latestMember.qr_token}</Text>
                </View>
              ) : null}
            </View>
          )}

          {activeTab === "members" && (
            <View style={styles.panel}>
              <Text style={styles.panelTitle}>Members and Credits</Text>
              <InputField
                label="Top-up Credits"
                value={topUpValue}
                onChangeText={setTopUpValue}
                keyboardType="numeric"
                placeholder="5"
              />
              <PrimaryButton label="Add Credits to Selected Member" onPress={handleTopUp} />
              <Text style={styles.helperText}>
                Selected member: {selectedMember ? selectedMember.full_name : "none"}
              </Text>

              <FlatList
                data={members}
                keyExtractor={(item) => item.id.toString()}
                scrollEnabled={false}
                ItemSeparatorComponent={() => <View style={styles.separator} />}
                renderItem={({ item }) => (
                  <TouchableOpacity
                    style={[
                      styles.memberCard,
                      item.id === selectedMemberId && styles.memberCardSelected,
                    ]}
                    onPress={() => setSelectedMemberId(item.id)}
                  >
                    <Text style={styles.memberName}>{item.full_name}</Text>
                    <Text style={styles.memberMeta}>Credits: {item.credits}</Text>
                    <Text style={styles.memberMeta}>Phone: {item.phone || "-"}</Text>
                  </TouchableOpacity>
                )}
              />
            </View>
          )}

          {activeTab === "scanner" && (
            <View style={styles.panel}>
              <Text style={styles.panelTitle}>QR Scanner</Text>
              {!permission?.granted ? (
                <View style={styles.permissionBox}>
                  <Text style={styles.helperText}>
                    Camera permission is needed to scan member QR codes.
                  </Text>
                  <PrimaryButton label="Allow Camera" onPress={requestPermission} />
                </View>
              ) : (
                <>
                  <View style={styles.cameraWrapper}>
                    <CameraView
                      style={styles.camera}
                      facing="back"
                      barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
                      onBarcodeScanned={handleScan}
                    />
                  </View>
                  <View style={scanCardStyle}>
                    <Text style={styles.scanText}>{scanMessage}</Text>
                  </View>
                  <Text style={styles.helperText}>
                    First valid scan today deducts one credit. Extra scans on the same day are marked as already scanned.
                  </Text>
                </>
              )}
            </View>
          )}

          {activeTab === "logs" && (
            <View style={styles.panel}>
              <Text style={styles.panelTitle}>Transaction Logs</Text>
              <FlatList
                data={logs}
                keyExtractor={(item) => item.id.toString()}
                scrollEnabled={false}
                ItemSeparatorComponent={() => <View style={styles.separator} />}
                renderItem={({ item }) => (
                  <View style={styles.logCard}>
                    <Text style={styles.memberName}>{item.full_name || "Unknown member"}</Text>
                    <Text style={styles.memberMeta}>Status: {item.status}</Text>
                    <Text style={styles.memberMeta}>
                      Credits: {item.credits_before} -> {item.credits_after}
                    </Text>
                    <Text style={styles.memberMeta}>{item.notes || "-"}</Text>
                    <Text style={styles.logDate}>{item.created_at}</Text>
                  </View>
                )}
              />
            </View>
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

function StatCard({ label, value }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

function InputField({ label, ...props }) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput style={styles.input} placeholderTextColor="#94a3b8" {...props} />
    </View>
  );
}

function PrimaryButton({ label, onPress }) {
  return (
    <TouchableOpacity style={styles.primaryButton} onPress={onPress}>
      <Text style={styles.primaryButtonText}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#f1f5f9",
  },
  container: {
    flex: 1,
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  header: {
    paddingTop: 12,
    paddingBottom: 10,
  },
  title: {
    fontSize: 26,
    fontWeight: "700",
    color: "#0f172a",
  },
  subtitle: {
    marginTop: 4,
    fontSize: 14,
    color: "#475569",
  },
  statsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginBottom: 14,
  },
  statCard: {
    flexGrow: 1,
    minWidth: "47%",
    backgroundColor: "#ffffff",
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: "#dbe2ea",
  },
  statLabel: {
    fontSize: 13,
    color: "#64748b",
  },
  statValue: {
    marginTop: 6,
    fontSize: 24,
    fontWeight: "700",
    color: "#0f172a",
  },
  tabsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
  },
  tabButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: "#e2e8f0",
    alignItems: "center",
  },
  tabButtonActive: {
    backgroundColor: "#2563eb",
  },
  tabText: {
    color: "#334155",
    fontWeight: "600",
  },
  tabTextActive: {
    color: "#ffffff",
  },
  content: {
    paddingBottom: 40,
  },
  panel: {
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#dbe2ea",
    borderRadius: 14,
    padding: 16,
  },
  panelTitle: {
    fontSize: 19,
    fontWeight: "700",
    color: "#0f172a",
    marginBottom: 12,
  },
  fieldGroup: {
    marginBottom: 12,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: "600",
    color: "#334155",
    marginBottom: 6,
  },
  input: {
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#cbd5e1",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
    color: "#0f172a",
  },
  primaryButton: {
    backgroundColor: "#2563eb",
    paddingVertical: 13,
    borderRadius: 10,
    alignItems: "center",
    marginTop: 4,
  },
  primaryButtonText: {
    color: "#ffffff",
    fontWeight: "700",
    fontSize: 15,
  },
  qrBox: {
    marginTop: 18,
    alignItems: "center",
    backgroundColor: "#f8fafc",
    borderWidth: 1,
    borderColor: "#dbe2ea",
    borderRadius: 12,
    padding: 16,
  },
  qrLabel: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 12,
    color: "#0f172a",
  },
  qrMeta: {
    marginTop: 10,
    color: "#475569",
    textAlign: "center",
  },
  helperText: {
    marginTop: 10,
    color: "#64748b",
    lineHeight: 20,
  },
  separator: {
    height: 10,
  },
  memberCard: {
    borderWidth: 1,
    borderColor: "#dbe2ea",
    borderRadius: 12,
    padding: 14,
    backgroundColor: "#ffffff",
  },
  memberCardSelected: {
    borderColor: "#2563eb",
    backgroundColor: "#eff6ff",
  },
  memberName: {
    fontSize: 16,
    fontWeight: "700",
    color: "#0f172a",
  },
  memberMeta: {
    marginTop: 4,
    color: "#475569",
  },
  cameraWrapper: {
    overflow: "hidden",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    height: 360,
  },
  camera: {
    flex: 1,
  },
  scanCard: {
    marginTop: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#dbe2ea",
    backgroundColor: "#f8fafc",
    padding: 16,
  },
  scanSuccess: {
    backgroundColor: "#ecfdf5",
    borderColor: "#86efac",
  },
  scanWarning: {
    backgroundColor: "#fffbeb",
    borderColor: "#fcd34d",
  },
  scanDanger: {
    backgroundColor: "#fef2f2",
    borderColor: "#fca5a5",
  },
  scanText: {
    fontSize: 18,
    fontWeight: "700",
    color: "#0f172a",
    textAlign: "center",
    lineHeight: 28,
  },
  permissionBox: {
    gap: 12,
  },
  logCard: {
    borderWidth: 1,
    borderColor: "#dbe2ea",
    borderRadius: 12,
    padding: 14,
    backgroundColor: "#ffffff",
  },
  logDate: {
    marginTop: 8,
    color: "#94a3b8",
    fontSize: 12,
  },
});
