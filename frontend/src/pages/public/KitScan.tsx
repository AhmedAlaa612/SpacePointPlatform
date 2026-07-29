import { useParams } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { getPublicKitApi } from "@/api/inventory"
import { PLAIN_LOGO } from "@/lib/logos"
import { BODY_BACKGROUND } from "@/lib/theme"

/**
 * What you get when you scan the QR on a kit. No login (I2-6).
 *
 * Deliberately says almost nothing: the label, what kind of kit it is, and
 * who to contact. Not where it lives, not who has it, not what's inside. A
 * code on a box that leaves the building is readable by whoever picks the box
 * up, and the useful case for a stranger scanning it is "I found this, whose
 * is it" — which needs an email address and nothing else.
 */
export default function KitScan() {
  const { kitToken } = useParams({ from: "/k/$kitToken" })
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-kit", kitToken],
    queryFn: () => getPublicKitApi(kitToken),
    retry: false,
  })

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-white" style={BODY_BACKGROUND}>
      <img src={PLAIN_LOGO} alt="SpacePoint" className="h-12 w-auto object-contain mb-8" />

      <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-black/30 backdrop-blur-xl p-6 text-center">
        {isLoading && <p className="text-sm text-white/70 py-6">Looking it up…</p>}

        {isError && (
          <div className="py-4">
            <p className="text-base font-semibold">We don&apos;t recognise this code</p>
            <p className="text-sm text-white/60 mt-1">
              It may have been retired, or the sticker may be damaged.
            </p>
          </div>
        )}

        {data && (
          <>
            <p className="font-mono text-2xl font-bold tracking-tight">{data.label}</p>
            <p className="text-sm text-white/70 mt-1">{data.template_name}</p>

            {data.status !== "working" && (
              <p className="mt-3 inline-block text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 capitalize">
                {data.status}
              </p>
            )}

            <hr className="my-5 border-white/10" />

            <p className="text-sm font-medium">Property of {data.owner}</p>
            <p className="text-sm text-white/60 mt-1">
              Found this? Please get in touch:
            </p>
            <a
              href={`mailto:${data.contact_email}?subject=Found ${encodeURIComponent(data.label)}`}
              className="text-sm font-medium text-primary hover:underline break-all"
            >
              {data.contact_email}
            </a>
          </>
        )}
      </div>
    </div>
  )
}
