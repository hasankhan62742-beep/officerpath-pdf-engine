// OfficerPath AI — /dashboard redirects to the profile page (M3).
// A bare /dashboard placeholder page is not allowed (M3 brief) —
// the full dashboard (stats, documents) is M4.

import { redirect } from "next/navigation";

export default function DashboardPage() {
  redirect("/dashboard/profile");
}
