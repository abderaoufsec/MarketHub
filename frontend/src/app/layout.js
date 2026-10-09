import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "../context/AuthContext";
import Header from "../components/common/Header";
import Footer from "../components/common/Footer";
import ToastProvider from "../components/common/Toaster";

const inter = Inter({ subsets: ["latin"] });

export const metadata = {
  title: "MarketHub - Your Online Marketplace",
  description:
    "Connect sellers and buyers through a simple, secure online marketplace",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className={inter.className}>
        <AuthProvider>
          <div className="flex flex-col min-h-screen">
            <Header />
            <main className="flex-grow bg-gray-50">{children}</main>
            <Footer />
          </div>
          <ToastProvider />
        </AuthProvider>
      </body>
    </html>
  );
}
