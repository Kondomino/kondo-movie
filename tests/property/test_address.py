import unittest
from src.property.address import Address

class TestAddress(unittest.TestCase):
    def test_standard_street_address(self):
        """Test a standard street address with house number, street name, and type."""
        address = Address("123 Main St, Boston, MA 02108, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "123 Main St, Boston")
        self.assertEqual(address.formatted_address_without_country, "123 Main St, Boston, MA, 02108")

    def test_apartment_address(self):
        """Test an address with apartment/unit number."""
        address = Address("212 W 18th St #PH2, New York, NY 10011, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "212 W 18th St, #PH2, New York")
        self.assertEqual(address.formatted_address_without_country, "212 W 18th St, #PH2, New York, NY, 10011")

    def test_suite_address(self):
        """Test an address with suite number."""
        address = Address("1600 Amphitheatre Parkway Suite 100, Mountain View, CA 94043, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "1600 Amphitheatre Parkway, Suite 100, Mountain View")
        self.assertEqual(address.formatted_address_without_country, "1600 Amphitheatre Parkway, Suite 100, Mountain View, CA, 94043")

    def test_rural_route_address(self):
        """Test a rural route address."""
        address = Address("RR 2 Box 152, Lockhart, TX 78644, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "RR 2 Box 152, Lockhart")
        self.assertEqual(address.formatted_address_without_country, "RR 2 Box 152, Lockhart, TX, 78644")

    def test_po_box_address(self):
        """Test a PO Box address."""
        address = Address("PO Box 123, Springfield, IL 62701, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "PO Box 123, Springfield")
        self.assertEqual(address.formatted_address_without_country, "PO Box 123, Springfield, IL, 62701")

    def test_address_with_directionals(self):
        """Test an address with directional prefixes and suffixes."""
        address = Address("789 N Main St Miami, FL 33130, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "789 N Main St, Miami")
        self.assertEqual(address.formatted_address_without_country, "789 N Main St, Miami, FL, 33130")

    def test_address_without_zip(self):
        """Test an address without ZIP code."""
        address = Address("456 Oak Avenue, Chicago, IL, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "456 Oak Avenue, Chicago")
        self.assertEqual(address.formatted_address_without_country, "456 Oak Avenue, Chicago, IL")

    def test_address_with_unit_letter(self):
        """Test an address with a unit letter."""
        address = Address("321 Pine St Unit B, Seattle, WA 98101, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "321 Pine St, Unit B, Seattle")
        self.assertEqual(address.formatted_address_without_country, "321 Pine St, Unit B, Seattle, WA, 98101")

    def test_address_with_floor(self):
        """Test an address with a floor number."""
        address = Address("555 Market St Floor #32, San Francisco, CA 94105, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "555 Market St, Floor #32, San Francisco")
        self.assertEqual(address.formatted_address_without_country, "555 Market St, Floor #32, San Francisco, CA, 94105")

    def test_address_with_building_name(self):
        """Test an address with a building name."""
        address = Address("Empire State Building, 350 5th Ave, New York, NY 10118, USA", Address.AddressInputType.FreeForm)
        self.assertEqual(address.short_formatted_address, "350 5th Ave, New York")
        self.assertEqual(address.formatted_address_without_country, "350 5th Ave, New York, NY, 10118")

if __name__ == '__main__':
    unittest.main() 