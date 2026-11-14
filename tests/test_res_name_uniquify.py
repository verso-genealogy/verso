import unittest

from verso.ru.targets.geni.translator import TerraformGenerator


def _hdr(rtype, name):
    return f'resource "{rtype}" "{name}" {{\n  x = 1\n}}\n'


class UniquifyResourceHeadersTest(unittest.TestCase):
    """`_uniquify_resource_headers` guarantees globally-unique Terraform
    resource names per type — same-№/same-name source records (scribal
    re-entries, twins, register overlaps) would otherwise emit duplicate
    `resource "T" "N"` blocks that Terraform rejects."""

    def _run(self, outputs):
        gen = TerraformGenerator(village_dir=None)
        gen._outputs = dict(outputs)
        gen._uniquify_resource_headers()
        return gen._outputs

    def test_first_wins_later_duplicates_suffixed(self):
        out = self._run({
            "a.tf": _hdr("geni_document", "death_of_matrona_d5")
                    + _hdr("geni_document", "death_of_matrona_d5")
                    + _hdr("geni_document", "death_of_matrona_d5"),
        })
        names = [ln.split('"')[3] for ln in out["a.tf"].splitlines()
                 if ln.startswith("resource ")]
        self.assertEqual(
            names,
            ["death_of_matrona_d5", "death_of_matrona_d5_2", "death_of_matrona_d5_3"],
        )

    def test_uniqueness_is_per_type(self):
        # Same name under two different resource types must NOT collide.
        out = self._run({
            "a.tf": _hdr("geni_profile", "x") + _hdr("geni_union", "x"),
        })
        self.assertIn('resource "geni_profile" "x" {', out["a.tf"])
        self.assertIn('resource "geni_union" "x" {', out["a.tf"])
        self.assertNotIn("x_2", out["a.tf"])

    def test_references_untouched(self):
        # A `geni_union` body references `geni_profile.x.id`; only the
        # duplicate *declaration* header is renamed, never the reference.
        body = ('resource "geni_union" "u" {\n'
                "  partners = [geni_profile.x.id]\n}\n")
        out = self._run({
            "a.tf": _hdr("geni_profile", "x") + _hdr("geni_profile", "x") + body,
        })
        self.assertIn("geni_profile.x.id", out["a.tf"])       # reference intact
        self.assertIn('resource "geni_profile" "x_2" {', out["a.tf"])  # dup renamed

    def test_cross_file_uniqueness(self):
        out = self._run({
            "a.tf": _hdr("geni_profile", "p"),
            "b.tf": _hdr("geni_profile", "p"),
        })
        # Sorted file order → a.tf keeps base, b.tf gets the suffix.
        self.assertIn('resource "geni_profile" "p" {', out["a.tf"])
        self.assertIn('resource "geni_profile" "p_2" {', out["b.tf"])

    def test_no_collision_is_noop(self):
        outputs = {"a.tf": _hdr("geni_profile", "p") + _hdr("geni_profile", "q")}
        self.assertEqual(self._run(outputs), outputs)


if __name__ == "__main__":
    unittest.main()
