import Link from "next/link";

export function Footer() {
    return (
        <footer className="py-6 border-t border-stone-200/60">
            <div className="max-w-7xl mx-auto px-6 lg:px-8 text-center">
                <p className="text-sm text-stone-500">
                    Designed and Developed by{" "}
                    <Link
                        href="https://gauravdatar.com"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-stone-700 hover:text-stone-900 font-medium transition-colors"
                    >
                        Gaurav Datar
                    </Link>
                </p>
            </div>
        </footer>
    );
}
