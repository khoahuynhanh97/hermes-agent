from hermes_personal.integrations.product_video.binding import ProductVideoBinding, ProductVideoBindingService, verify_binding_integrity


def test_binding_creation_and_digest_match():
    service = ProductVideoBindingService()
    product_id = "prod-123"
    resource_pack = {"data": [1, 2, 3], "meta": {"version": 1}}
    binding = service.create_binding(product_id, resource_pack)
    assert isinstance(binding, ProductVideoBinding)
    assert binding.product_id == product_id
    # verify integrity should be true for same pack
    assert verify_binding_integrity(binding, resource_pack)


def test_binding_invalidates_on_pack_change():
    service = ProductVideoBindingService()
    product_id = "prod-123"
    resource_pack = {"data": [1, 2, 3], "meta": {"version": 1}}
    binding = service.create_binding(product_id, resource_pack)
    # modify pack
    altered_pack = {"data": [1, 2, 3, 4], "meta": {"version": 1}}
    assert not verify_binding_integrity(binding, altered_pack)
